"""DA8 production board tests. Normal Modbus commands, raw NTC input only.

No derived temperatures, output, PID, fault or timer state is written. Software
DA/PWM/GPIO readings do not measure terminal voltage or mechanical valve travel.
"""
import json
import math
import struct
import threading
import time
import traceback
from contextlib import ExitStack

import deploy_da8_manual_v1074_20261124 as dep

d, DAY = dep.d, dep.DAY


def signed(v):return v-65536 if v>=32768 else v


class Bench:
    record_name='board_manual'

    def stopped_snapshot(self,s):return d.stopped(s)

    def __init__(self):
        self.path=DAY/(self.record_name+'.json')
        assert not self.path.exists(), 'Preserve previous board test'
        assert json.loads((DAY/'deployment.json').read_text('utf8'))['passed']
        self.c=d.client();self.stack=ExitStack();self.targets=[];self.sy=[]
        self.lock=threading.RLock();self.stop_input=threading.Event();self.worker_error=None
        self.raw={};self.touched=set();self.original=d.config(self.c)
        self.log=dict(started=d.now(),original=self.original,writes=[],cases=[],passed=False,
            physical_terminal_measurement=False,derived_state_writes=False,
            input_scope='NTC0/1/2 acquisition ADbuffer, NTC_AD and raw20-sample filters only')
        assert self.stopped_snapshot(d.snap(self.c))
        assert self.rd(2622,18)==dep.EXPECTED
        for board in dep.BOARDS:
            image=dep.NEW if board[0]=='330' else board[6]
            ss=self.stack.enter_context(d.ConnectHelper.session_with_chosen_probe(
                unique_id=board[1],target_override=board[2],options={
                'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}))
            d.verify(ss.target,image)
            self.targets.append(ss.target);self.sy.append(d.symbols(image.with_suffix('.axf')))
        self.t=self.targets[2];self.sym=self.sy[2];self.p=self.sym['Parameter']
        self.table=struct.unpack('<201f',bytes(self.t.read_memory_block8(self.sym['NTCtable'],804)))
        self.samples=(DAY/(self.record_name+'_samples.jsonl')).open('x',encoding='utf8',buffering=1)
        self.thread=threading.Thread(target=self.worker,daemon=True);self.thread.start()
        self.save()

    def save(self):dep.dump(self.path,self.log)
    def rd(self,a,n=1):return self.c.read_holding_registers(1,a,n)
    def wr(self,a,v):
        if str(a) not in self.original:self.original[str(a)]=self.rd(a)[0]
        if a not in (398,524,245):self.touched.add(a)
        event=dict(at=d.now(),t=time.monotonic(),address=a,value=v,route='normal330_Modbus')
        self.log['writes'].append(event);self.save()
        self.c.write_single_register(1,a,v&65535)
        if a not in (398,524,245):assert self.rd(a)==[v&65535],(a,v,self.rd(a))

    def config(self,values):
        for a,v in values.items():
            if self.rd(a)!=[v&65535]:self.wr(a,v)

    def temperature(self,ch,temp10):
        calibration=signed(self.rd(495-ch)[0])
        degrees=(temp10-calibration)/10
        idx=math.floor(degrees)+50;fraction=degrees-(idx-50)
        resistance=self.table[idx]+fraction*(self.table[idx+1]-self.table[idx])
        raw=round(2.048*resistance/(5.1+resistance)/.0000625)
        with self.lock:self.raw[ch]=raw
        self.log.setdefault('input_events',[]).append(dict(at=d.now(),t=time.monotonic(),
            channel=ch,requested10=temp10,calibration10=calibration,raw=raw))
        self.save()

    def worker(self):
        try:
            while not self.stop_input.is_set():
                with self.lock:
                    for ch,raw in self.raw.items():
                        self.t.write16(self.sym['ADbuffer']+2*ch,raw)
                        self.t.write_memory_block8(self.sym['NTC_Val_Filter']+40*ch,
                            list(struct.pack('<20H',*([raw]*20))))
                        self.t.write16(self.sym['NTC_AD']+2*ch,raw)
                    self.t.flush()
                self.stop_input.wait(.004)
        except BaseException:self.worker_error=traceback.format_exc()

    @staticmethod
    def u16(t,address):
        return (t.read32(address&~3)>>(8*(address&3)))&65535

    def capture(self,label):
        assert not self.worker_error,self.worker_error
        began=time.monotonic()
        with self.lock:
            p=lambda a:self.u16(self.t,self.p+2*a)
            da_addr=self.sym['DA']
            words={a:self.t.read32(a) for a in range(da_addr&~3,((da_addr+19)&~3)+1,4)}
            da=[(words[a&~3]>>(8*(a&3)))&65535 for a in range(da_addr,da_addr+20,2)]
            z=dict(at=d.now(),t=began,label=label,step=p(709),mode=p(236),
                configured_mode=p(1),command=p(398),fault_status=p(710),
                fresh10=signed(p(512)),room10=signed(p(511)),control10=signed(p(738)),
                manual=p(247),minimum=p(346),legacy=p(245),da=da,
                display=p(925),final=p(922),pwm=self.t.read32(0x4000043c)&65535,
                indoor_faults=[p(a) for a in range(594,627)],
                sensor_partial_stop=self.t.read8(self.sym['IndoorSensorPartialStopFlag']),
                input_raw={ch:self.u16(self.t,self.sym['NTC_AD']+2*ch) for ch in self.raw},
                indoor_do=[p(a) for a in range(814,822)])
        outputs=[]
        for t,sy in zip(self.targets[:2],self.sy[:2]):
            pb,pd=t.read32(0x40010c0c),t.read32(0x4001140c)
            outputs.append(dict(gpio=[(pb>>(12+i))&1 for i in range(4)]+
                [(pd>>(8+i))&1 for i in range(4)],
                faults=[self.u16(t,sy['Parameter']+2*a) for a in range(594,624)]))
        z['outdoor']=outputs;z['read_bounds']=[began,time.monotonic()]
        self.samples.write(json.dumps(z,ensure_ascii=False,separators=(',',':'))+'\n')
        return z

    def row(self,name):
        row=dict(name=name,started=d.now(),samples=0,passed=False)
        self.log['cases'].append(row);self.save();return row

    def wait(self,row,predicate,timeout=50,healthy=True,hold=0):
        began=time.monotonic();matched=None;notice=0
        while True:
            z=self.capture(row['name']);row['samples']+=1;row['last']=z
            assert not any(v for out in z['outdoor'] for v in out['gpio'][:2]),('Unexpected compressor load',z)
            if healthy:
                assert not any(z['indoor_faults']) and not z['sensor_partial_stop'],('Unexpected indoor fault',z)
                assert not any(v for o in z['outdoor'] for v in o['faults']),('Unexpected outdoor fault',z)
            if predicate(z):
                if matched is None:matched=z['t'];row['first_match']=z
                if z['t']-matched>=hold:
                    row.update(passed=True,elapsed_s=time.monotonic()-began,hold_s=hold,
                        finished=d.now());self.save()
                    print('PASS',row['name'],'fresh',z['fresh10'],'DA8',z['da'][8],
                        'PWM',z['pwm'],'step',z['step'],flush=True)
                    return z
            else:matched=None
            assert time.monotonic()-began<timeout,('Case timeout',row['name'],z)
            if time.monotonic()-notice>20:
                print('WAIT',row['name'],'elapsed',round(time.monotonic()-began,1),
                    'step',z['step'],'fresh',z['fresh10'],'DA8',z['da'][8],flush=True)
                self.save();notice=time.monotonic()
            time.sleep(.15)

    @staticmethod
    def output(z,expected):
        return [z['display'],z['final'],z['da'][8],z['pwm']]==[expected,expected,expected,expected*98//100]

    def check(self,name,value,minimum,fresh,expected,mode,hold=3):
        self.config({247:value,346:minimum});self.temperature(2,fresh)
        row=self.row(name)
        row.update(requested_manual=value,requested_minimum=minimum,
            requested_fresh10=fresh,expected_output=expected,mode=mode)
        return self.wait(row,lambda z:z['step']==2 and z['mode']==mode and z['fresh10']==fresh
            and z['manual']==value and z['minimum']==minimum and z['legacy']==1
            and self.output(z,expected) and all(z['da'][i]==0 for i in (0,1,9)),hold=hold)

    def normal_stop(self,label):
        row=self.row(label);row['command_t']=time.monotonic();self.wr(398,0)
        return self.wait(row,lambda z:z['step']==0 and z['command']==0 and not any(z['da'])
            and not any(v for o in z['outdoor'] for v in o['gpio']),timeout=200,hold=2)

    def finish(self):
        try:
            self.normal_stop('final normal stop before restoring baseline')
            for a in sorted(self.touched):
                if a not in (236,164):self.c.write_single_register(1,a,self.original[str(a)])
            for a in (236,164):
                if a in self.touched:self.c.write_single_register(1,a,self.original[str(a)])
            self.stop_input.set();self.thread.join(10)
            assert not self.thread.is_alive() and not self.worker_error,self.worker_error
            began=time.monotonic()
            while True:
                actual=d.config(self.c)
                mismatch={str(a):[self.original[str(a)],actual[str(a)]] for a in self.touched
                    if actual[str(a)]!=self.original[str(a)]}
                self.log.update(restoration_mismatches=mismatch,final_snapshot=d.snap(self.c))
                self.save()
                if not mismatch and self.stopped_snapshot(self.log['final_snapshot']) and not any(self.log['final_snapshot']['594']):break
                assert time.monotonic()-began<60,mismatch
                time.sleep(.5)
            self.log['restored']=True
        except BaseException:
            self.log['cleanup_error']=traceback.format_exc();raise
        finally:
            self.stop_input.set();self.thread.join(10)
            self.stack.close();self.c.close();self.samples.close()
            self.log['finished']=d.now();self.save()


def main():
    b=Bench()
    try:
        b.temperature(0,250);b.temperature(1,250);b.temperature(2,100)
        b.config({163:0,164:0,165:0,236:0,127:0,128:0,129:1,125:0,126:0,
            248:0,315:0,320:0,332:0,333:0,334:0,335:0,336:0,337:0,338:0,
            160:320,161:250,346:0,247:1000})
        row=b.row('stopped manual1000 does not energize DA8')
        b.wait(row,lambda z:z['step']==0 and b.output(z,0) and z['legacy']==1,hold=3)
        row=b.row('normal cooling start at zero compressor demand');b.wr(398,1)
        b.wait(row,lambda z:z['step']==2 and z['mode']==0 and z['fresh10']==100
            and b.output(z,1000),timeout=150,hold=3)
        for mode in (0,1):
            if mode:
                b.normal_stop('cooling normal shutdown before heating cases')
                b.config({236:1,346:0,247:0})
                row=b.row('normal heating start with HeatMode0 and manual0');b.wr(398,1)
                b.wait(row,lambda z:z['step']==2 and z['mode']==1 and b.output(z,0),timeout=160,hold=2)
            for value in (0,100,300,500,1000):
                b.check(f'mode{mode} warm manual{value}',value,200,100,value,mode)
            for fresh in (-1,0,1):
                b.check(f'mode{mode} exact fresh boundary{fresh/10}C',0,200,fresh,
                    200 if fresh<0 else 0,mode)
            b.check(f'mode{mode} cold manual above minimum',500,200,-1,500,mode)
            b.check(f'mode{mode} cold minimum disabled',0,0,-1,0,mode)
            b.check(f'mode{mode} cold minimum full scale',100,1000,-1,1000,mode)
            b.check(f'mode{mode} legacy trend setup baseline',300,0,100,300,mode)
            b.wr(246,500)
            for temp in (220,270,250):
                b.temperature(0,temp);b.temperature(1,temp)
                row=b.row(f'mode{mode} room{temp/10}C cannot change manual300')
                b.wait(row,lambda z:z['step']==2 and z['room10']==temp and b.output(z,300),hold=3)
            row=b.row(f'mode{mode} legacy automatic request remains manual')
            try:b.wr(245,0)
            except Exception as exc:row['normal_write_rejection']=str(exc)
            b.wait(row,lambda z:z['legacy']==1 and b.output(z,300),hold=3)
            b.check(f'mode{mode} cold preparation for normal shutdown',0,200,-1,200,mode)
        # Required fresh-air sensor failure is stimulated at acquisition, never by
        # setting a derived temperature or fault flag.
        b.check('fresh sensor failure preparation manual500',500,200,100,500,1)
        with b.lock:b.raw[2]=32767
        row=b.row('invalid required fresh probe alarms and closes DA8')
        row['raw_stimulus']=32767
        b.wait(row,lambda z:z['fresh10']==9999 and z['sensor_partial_stop']==1
            and z['indoor_faults'][6]==1 and b.output(z,0),timeout=40,healthy=False,hold=3)
        b.temperature(2,100)
        row=b.row('valid fresh probe restored through normal fault processing')
        b.wr(524,1);time.sleep(.3);b.wr(524,0)
        b.wait(row,lambda z:z['fresh10']==100 and not any(z['indoor_faults'])
            and not z['sensor_partial_stop'] and b.output(z,500),healthy=False,timeout=50,hold=3)
        b.check('heating cold minimum before final normal stop',0,200,-1,200,1)
        b.log['sequence_completed']=True;b.save()
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    b.log['passed']=all(row['passed'] for row in b.log['cases']) and b.log.get('restored',False)
    b.save()
    assert b.log['passed']
    print('BOARD DA8 PASS',len(b.log['cases']),'cases; parameters restored and stopped',flush=True)


if __name__=='__main__':main()
