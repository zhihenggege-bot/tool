"""X11/X12 overload and X14/X15 pressure: actual production elapsed timing.

Only normal Modbus settings/start/stop/reset/polarity commands. SWD read-only.
No physical contact switching or terminal voltage measurement is implied.
"""
import json
import struct
import sys
import time
import traceback
from contextlib import ExitStack
from pathlib import Path
import deploy_di_faults_v1076_20261124 as deploy

dep=deploy.configure();d=dep.d
import app
DAY=dep.R/'测试证据/风机四路DI_V1076_20261124'


class Bench:
    def __init__(self):
        DAY.mkdir(exist_ok=True)
        self.path=DAY/'board.json';assert not self.path.exists()
        self.c=d.client();self.stack=ExitStack();self.targets=[];self.sy=[]
        self.original=d.config(self.c);self.touched=set()
        self.log=dict(started=d.now(),passed=False,original=self.original,writes=[],checks=[],events=[],
            physical_contacts_switched=False,physical_terminal_measured=False,target_memory_writes=False,
            scope='Normal330 Modbus input-polarity simulation; formal wall-clock timing; read-only SWD; ventilation, outdoor compressors remain stopped')
        assert dep.POSTBOOT_STOPPED(d.snap(self.c))
        assert self.rd(2622,18)==dep.EXPECTED
        for bd in dep.BOARDS:
            image=dep.NEW if bd[0]=='330' else bd[6]
            ss=self.stack.enter_context(d.ConnectHelper.session_with_chosen_probe(unique_id=bd[1],target_override=bd[2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}))
            d.verify(ss.target,image)
            self.targets.append(ss.target);self.sy.append(d.symbols(image.with_suffix('.axf')))
        self.t=self.targets[2];self.sym=self.sy[2]
        self.samples=(DAY/'samples.jsonl').open('x',encoding='utf8',buffering=1)
        self.previous=None;self.last_notice=0
        self.save()

    def rd(self,a,n=1):return self.c.read_holding_registers(1,a,n)
    def save(self):dep.dump(self.path,self.log)
    def check(self,name,ok,**details):
        self.log['checks'].append(dict(name=name,passed=bool(ok),**details));self.save()
        assert ok,(name,details)
        print('PASS',name,flush=True)

    def wr(self,a,v):
        assert a<500 or a in (524,),'Normal settings or fault reset only'
        if a not in (398,524):self.touched.add(a)
        self.log['writes'].append(dict(at=d.now(),t=time.monotonic(),address=a,value=v))
        self.save();self.c.write_single_register(1,a,v&65535)
        if a!=398:assert self.rd(a)==[v&65535],(a,v,self.rd(a))

    def config(self,values):
        for a,v in values.items():
            if self.rd(a)!=[v&65535]:self.wr(a,v)

    def sample(self,label):
        began=time.monotonic();v={}
        for a,n in ((594,33),(700,11),(814,8),(861,1),(888,2),(909,5),(956,13),(1350,24)):
            v.update({a+i:x for i,x in enumerate(self.rd(a,n))})
        raw=list(self.t.read_memory_block8(self.sym['input'],14))
        adjusted={s:self.t.read8(self.sym[s]) for s in ('X_11','X_12','X_14','X_15')}
        out=list(self.t.read_memory_block8(self.sym['output'],16))
        da=list(struct.unpack('<10H',bytes(self.t.read_memory_block8(self.sym['DA'],20))))
        outdoor=[]
        for t in self.targets[:2]:
            pb,pd=t.read32(0x40010c0c),t.read32(0x4001140c)
            outdoor.append([(pb>>(12+i))&1 for i in range(4)]+[(pd>>(8+i))&1 for i in range(4)])
        z=dict(at=d.now(),t=began,read_ended=time.monotonic(),label=label,values=v,
            raw_input=raw,adjusted=adjusted,indoor_output=out,da=da,outdoor_gpio=outdoor)
        self.samples.write(json.dumps(z,ensure_ascii=False,separators=(',',':'))+'\n')
        edges={str(a):v[a] for a in (605,709,710,819,861,912,913,956,958,1366,817,820)
            if self.previous is None or self.previous['values'][a]!=v[a]}
        if edges:self.log['events'].append(dict(at=z['at'],t=began,label=label,edges=edges));self.save()
        self.previous=z
        assert not any(g[i] for g in outdoor for i in (0,1)),('Unexpected compressor output',z)
        assert not any(v[a] for a in range(594,627) if a!=605),('Unexpected unrelated indoor fault',z)
        if began-self.last_notice>20:
            print('TRACE',label,'step',v[709],'fans',[out[i] for i in (3,6,8)],
                'faults',[v[a] for a in (956,958,913,912)],'Y05',v[819],flush=True)
            self.last_notice=began
        return z

    def wait(self,label,predicate,timeout=20,hold=.3):
        began=time.monotonic();matched=None
        while True:
            z=self.sample(label)
            if predicate(z):
                if matched is None:matched=z['t']
                if z['t']-matched>=hold:
                    self.check(label,True,elapsed_s=time.monotonic()-began,last=z)
                    return z
            else:matched=None
            if time.monotonic()-began>timeout:self.check(label,False,last=z,timeout=timeout)
            time.sleep(.08)

    def observe(self,label,seconds,predicate):
        began=time.monotonic();last=None
        while time.monotonic()-began<seconds:
            last=self.sample(label)
            if not predicate(last):self.check(label,False,last=last)
            time.sleep(.08)
        self.check(label,True,elapsed_s=time.monotonic()-began,last=last)
        return last

    def contact(self,ch,desired):
        idx={'11':9,'12':10,'14':12,'15':13}[ch]
        reg={'11':393,'12':394,'14':396,'15':397}[ch]
        raw=self.t.read8(self.sym['input']+idx)
        polarity=1 if raw==desired else 0
        began=time.monotonic();self.config({reg:polarity})
        self.wait(f'X{ch} adjusted input={desired}',lambda z:z['adjusted']['X_'+ch]==desired,timeout=4,hold=0)
        return began

    def reset(self):
        self.wr(524,1);time.sleep(.15);self.wr(524,0)

    def stop(self,label):
        self.wr(398,0)
        return self.wait(label,lambda z:z['values'][709]==0 and not any(z['indoor_output'][i] for i in (3,6,8)),
            timeout=110,hold=.5)

    def healthy(self):
        for ch in ('11','12'):self.contact(ch,0)
        for ch in ('14','15'):self.contact(ch,1)
        self.observe('settle original3s input filters',.6,lambda z:True)
        self.reset()
        self.wait('faults and Y05 clear',lambda z:not any(z['values'][a] for a in (605,710,819,861,912,913,956,958)))

    def setup(self,return_mode=1,exhaust_mode=1,pressure=0,supply_mode=1):
        self.stop('stop before next configuration');self.healthy()
        self.config({163:0,164:0,165:0,236:2,329:supply_mode,330:return_mode,331:exhaust_mode,
            132:0,135:0,131:50,134:50,386:pressure,
            335:0,336:0,337:0,338:0,127:0,128:0,332:0,333:0,334:0,
            248:0,320:0})

    def start(self,label):
        began=time.monotonic();self.wr(398,1)
        z=self.wait(label,lambda z:z['values'][709]==2,timeout=65)
        return z,began

    def overload(self,ch,return_mode=1):
        fault=956 if ch=='11' else 958
        self.setup(return_mode=return_mode,exhaust_mode=1)
        z,_=self.start(f'X{ch} mode{return_mode} normal ventilation running')
        output_idx=8 if ch=='11' else 6
        self.check(f'X{ch} corresponding fan output on',z['indoor_output'][output_idx]==1
            and (ch!='12' or return_mode!=2 or z['da'][4]>0))
        self.contact(ch,1)
        self.observe(f'X{ch} short pulse no alarm',1.0,lambda z:z['values'][fault]==0)
        self.contact(ch,0)
        self.observe(f'X{ch} interrupted pulse clears timer',.5,lambda z:z['values'][fault]==0)
        began=self.contact(ch,1)
        z=self.wait(f'X{ch} fault{fault} and alarm trip',lambda z:z['values'][fault]==1
            and z['values'][819]==z['values'][861]==z['values'][605]==1,timeout=8)
        self.log.setdefault('timings',[]).append(dict(test=f'X{ch} overload mode{return_mode}',
            input_write_t=began,first_confirmed_t=z['t'],observed_delay_s=z['t']-began))
        self.wait(f'X{ch} protection stops all indoor fans',lambda z:not any(z['indoor_output'][i] for i in (3,6,8))
            and z['values'][709]==0)
        self.wr(398,0);self.reset()
        self.wait(f'X{ch} active overcurrent prevents clearing latch',lambda z:z['values'][fault]==1 and z['values'][819]==1)
        self.contact(ch,0)
        self.wait(f'X{ch} input normal',lambda z:z['values'][1359 if ch=='11' else 1360]==0)
        self.observe(f'X{ch} input restored retains fault',.8,lambda z:z['values'][fault]==1)
        self.reset();self.wait(f'X{ch} reset clears fault',lambda z:z['values'][fault]==0 and z['values'][819]==0)

    def pressure(self,ch,fan_mode):
        fault=912 if ch=='15' else 913
        other=913 if ch=='15' else 912
        self.setup(return_mode=fan_mode if ch=='14' else 0,exhaust_mode=0,
            pressure=2 if ch=='15' else 3,supply_mode=fan_mode if ch=='15' else 1)
        self.contact(ch,0)
        start=time.monotonic();self.wr(398,1)
        idx=3 if ch=='15' else 6
        on=self.wait(f'X{ch} corresponding fan starts',lambda z:z['indoor_output'][idx]==1,timeout=30,hold=0)
        fan_on=on['t']
        self.observe(f'X{ch} before60s absent pressure no alarm',2.0,lambda z:z['values'][fault]==0)
        began=self.contact(ch,1)
        self.observe(f'X{ch} short startup pressure insufficient',3.0,lambda z:z['values'][709]==1 and z['values'][fault]==0)
        self.contact(ch,0)
        self.wait(f'X{ch} startup qualification interrupted',lambda z:z['values'][888 if ch=='15' else 889]==0)
        qualified_from=self.contact(ch,1)
        ready=self.wait(f'X{ch} startup needs continuous10s permission',lambda z:z['values'][709]==2,timeout=17,hold=0)
        self.check(f'X{ch} formal qualification at least9.5s',ready['t']-qualified_from>=9.5,
            elapsed_s=ready['t']-qualified_from)
        # Record real60s fan runtime; no timer writes or accelerated profile.
        while time.monotonic()-fan_on<61.5:
            z=self.sample(f'X{ch} wait real60s fan gate')
            assert z['values'][fault]==z['values'][other]==0
            time.sleep(.2)
        self.contact(ch,0)
        self.observe(f'X{ch} short7s pressure loss no alarm',7.0,lambda z:z['values'][fault]==0)
        self.contact(ch,1)
        self.observe(f'X{ch} restored permission cancels bad timer',.8,lambda z:z['values'][fault]==0)
        began=self.contact(ch,0)
        trip=self.wait(f'X{ch} continuous10s trips only{fault}',lambda z:z['values'][fault]==1
            and z['values'][other]==0 and z['values'][819]==z['values'][861]==1,timeout=16,hold=0)
        self.check(f'X{ch} no early10s trip',trip['t']-began>=9.5,observed_s=trip['t']-began)
        self.log.setdefault('timings',[]).append(dict(test=f'X{ch} pressure fanmode{fan_mode}',
            fan_first_seen_t=fan_on,startup_qualification_s=ready['t']-qualified_from,
            fault_input_write_t=began,fault_first_seen_t=trip['t'],observed_delay_s=trip['t']-began))
        self.wr(398,0)
        self.wait(f'X{ch} protection stops indoor fan outputs',lambda z:not any(z['indoor_output'][i] for i in (3,6,8))
            and z['values'][709]==0,timeout=105)
        self.contact(ch,1)
        self.observe(f'X{ch} restored pressure retains fault until reset',.8,lambda z:z['values'][fault]==1)
        self.reset();self.wait(f'X{ch} normal reset clears fault and Y05',lambda z:z['values'][fault]==0 and z['values'][819]==0)

    def finish(self):
        try:
            self.stop('final normal stop')
            self.healthy()
            # Restore only settings actually changed; mode last, after full stop.
            for a in sorted(self.touched-{236}):self.wr(a,self.original[str(a)])
            if 236 in self.touched:self.wr(236,self.original['236'])
            self.wait('baseline inputs and faults restored',lambda z:z['values'][709]==0
                and not any(z['values'][a] for a in (605,710,819,861,912,913,956,958)),timeout=15)
            actual=d.config(self.c)
            changes={a:[v,actual[a]] for a,v in self.original.items() if v!=actual[a]}
            self.log['readonly_counter_changes']={a:v for a,v in changes.items() if int(a) in (1875,1923)}
            mismatch={a:v for a,v in changes.items() if int(a) not in (1875,1923)}
            self.log['configuration_mismatches']=mismatch
            assert not mismatch,mismatch
            self.log['final_snapshot']=d.snap(self.c)
            assert dep.POSTBOOT_STOPPED(self.log['final_snapshot'])
            self.log['restored']=True
        except BaseException:
            self.log['cleanup_error']=traceback.format_exc();raise
        finally:
            self.samples.close();self.stack.close();self.c.close()
            self.log['finished']=d.now();self.save()


def main():
    b=Bench()
    try:
        b.overload('11')
        b.overload('12',1)
        b.overload('12',2)
        b.pressure('15',1)
        b.pressure('14',2)
        b.log['sequence_completed']=True
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    b.log['passed']=b.log.get('sequence_completed',False) and b.log.get('restored',False)
    b.save();assert b.log['passed']
    print('FAN DI BOARD PASS',len(b.log['checks']),'checks; all settings restored',flush=True)


if __name__=='__main__':main()
