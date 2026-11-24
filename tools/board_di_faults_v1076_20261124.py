"""Production board DI diagnostics via normal polarity/reset commands only.

SWD is read-only. Physical contacts remain unchanged. Both physical-input
directions were tested offline; this run tests inversion against live inputs.
"""
import json
import struct
import time
import traceback
from contextlib import ExitStack
import tkinter as tk
import build_di_faults_v1076_20261124 as build
import deploy_di_faults_v1076_20261124 as deploy

dep=deploy.configure()
d=dep.d
import app

POINTS=(('fire',1,156,1351,960),('valve',4,159,1354,962),('leak',11,395,1361,964))


class Bench:
    def __init__(self):
        self.path=build.DAY/'board_DI.json'
        assert not self.path.exists(),'Preserve previous board evidence'
        self.c=d.client();self.stack=ExitStack()
        self.targets=[];self.symbols=[]
        self.original=d.config(self.c)
        self.log=dict(started=d.now(),passed=False,writes=[],checks=[],cases=[],
            original=self.original,physical_contacts_switched=False,physical_terminal_measured=False,
            target_memory_writes=False,scope='Live raw input read-only; normal330 polarity/reset writes; stopped unit')
        assert json.loads((build.DAY/'deployment.json').read_text('utf8'))['passed']
        assert dep.POSTBOOT_STOPPED(d.snap(self.c))
        for board in dep.BOARDS:
            image=dep.NEW if board[0]=='330' else board[6]
            ss=self.stack.enter_context(d.ConnectHelper.session_with_chosen_probe(unique_id=board[1],
                target_override=board[2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}))
            d.verify(ss.target,image)
            self.targets.append(ss.target);self.symbols.append(d.symbols(image.with_suffix('.axf')))
        self.samples=(build.DAY/'board_DI_samples.jsonl').open('x',encoding='utf8',buffering=1)
        self.root=tk.Tk();self.root.withdraw()
        self.table=app.RegisterTable(self.root,'Live DI',app.INDOOR_DI_PROTECTIONS)
        self.save()

    def save(self):dep.dump(self.path,self.log)

    def check(self,name,ok,**details):
        self.log['checks'].append(dict(name=name,passed=bool(ok),**details));self.save()
        assert ok,(name,details)

    def wr(self,a,v):
        assert a in (156,159,395,524),'Only normal DI polarity/reset commands permitted'
        self.log['writes'].append(dict(at=d.now(),t=time.monotonic(),address=a,value=v))
        self.save();self.c.write_single_register(1,a,v)
        assert self.c.read_holding_registers(1,a,1)==[v]

    def capture(self,label):
        began=time.monotonic();values={}
        for a,n in ((2622,6),(594,54),(709,2),(814,8),(861,1),(909,5),(956,13),(1350,14)):
            values.update({a+i:v for i,v in enumerate(self.c.read_holding_registers(1,a,n))})
        t=self.targets[2];sy=self.symbols[2]
        raw=list(t.read_memory_block8(sy['input'],14))
        filtered=[t.read8(sy[name]) for name in ('X01_En','X04_En','X13_En')]
        counters=[t.read16(sy[name]) for name in ('X01_Cnt','X04_Cnt','X13_Cnt')]
        outdoor=[]
        for ot in self.targets[:2]:
            pb,pd=ot.read32(0x40010c0c),ot.read32(0x4001140c)
            outdoor.append([(pb>>(12+i))&1 for i in range(4)]+[(pd>>(8+i))&1 for i in range(4)])
        self.table.update_values(values)
        displayed={str(a):self.table.tree.item(str(a))['values'][4] for a in (960,962,964)}
        z=dict(at=d.now(),t=began,label=label,read_ended=time.monotonic(),values=values,
            raw_input=raw,filtered_input=filtered,filter_counts=counters,outdoor_gpio=outdoor,
            rendered=displayed)
        self.samples.write(json.dumps(z,ensure_ascii=False,separators=(',',':'))+'\n')
        assert values[709]==0,('Unexpected unit startup',z)
        assert not any(v for channel in outdoor for v in channel[:2]),('Unexpected compressor output',z)
        assert not any(values[a] for a in range(814,822) if a!=819),('Unexpected indoor DO',z)
        assert not any(values[a] for a in range(594,627) if a!=605),('Unexpected unrelated indoor fault',z)
        return z

    def wait(self,label,predicate,timeout=10,hold=.35):
        began=time.monotonic();matched=None;samples=0
        while True:
            z=self.capture(label);samples+=1
            if predicate(z):
                if matched is None:matched=z['t']
                if z['t']-matched>=hold:
                    self.check(label,True,elapsed_s=time.monotonic()-began,samples=samples,last=z)
                    print('PASS',label,'faults',[z['values'][a] for a in (960,962,964)],
                        'Y05',z['values'][819],flush=True)
                    return z
            else:matched=None
            if time.monotonic()-began>=timeout:
                self.check(label,False,timeout_s=timeout,last=z)
            time.sleep(.05)

    @staticmethod
    def expected(z,mask,alarm):
        v=z['values']
        return [v[a] for a in (960,962,964)]==list(mask) and v[605]==v[861]==v[819]==alarm

    def reset(self):
        self.wr(524,1);time.sleep(.2);self.wr(524,0)

    def recover(self,label):
        for _,_,a,_,_ in POINTS:
            self.wr(a,self.original[str(a)])
        self.wait(label+' inputs normal',lambda z:all(z['values'][a]==0 for a in (1351,1354,1361)))
        self.reset()
        return self.wait(label+' no alarms',lambda z:self.expected(z,(0,0,0),0))

    def individual(self,point,repeat):
        name,ch,polarity_reg,input_reg,fault_reg=point
        row=dict(name=name,repeat=repeat,started=d.now());self.log['cases'].append(row);self.save()
        self.recover(f'{name}{repeat} baseline')
        raw=self.targets[2].read8(self.symbols[2]['input']+ch)
        original=self.original[str(polarity_reg)]
        self.check(f'{name}{repeat} physical input stable and original polarity healthy',
            raw in (0,1) and (raw if original else 1-raw)==0,raw=raw,polarity=original)
        if repeat==1:
            start=time.monotonic();self.wr(polarity_reg,1-original)
            # A short sub-three-second input must not confirm any fault.
            while time.monotonic()-start<1.3:
                z=self.capture(name+' short pulse')
                self.check(f'{name} short pulse below3s no fault',self.expected(z,(0,0,0),0))
            self.wr(polarity_reg,original)
            self.wait(name+' short pulse interrupted',lambda z:self.expected(z,(0,0,0),0)
                and z['values'][input_reg]==0,hold=.5)
        began=time.monotonic();self.wr(polarity_reg,1-original)
        mask=tuple(int(a==fault_reg) for a in (960,962,964))
        z=self.wait(f'{name}{repeat} independent fault and Y05',lambda z:self.expected(z,mask,1)
            and z['values'][input_reg]==1)
        row['first_confirmed_after_write_s']=z['t']-began
        row['raw_contact']=raw;row['trigger_polarity']=1-original
        self.check(f'{name}{repeat} monitor shows confirmed fault',z['rendered'][str(fault_reg)]=='故障/报警已置位')
        self.reset()
        self.wait(f'{name}{repeat} active fault reasserts after reset',lambda z:self.expected(z,mask,1))
        self.wr(polarity_reg,original)
        self.wait(f'{name}{repeat} input normal but cause remains latched',lambda z:self.expected(z,mask,1)
            and z['values'][input_reg]==0,hold=.6)
        self.reset()
        self.wait(f'{name}{repeat} normal reset clears fault and Y05',lambda z:self.expected(z,(0,0,0),0))
        row.update(passed=True,finished=d.now());self.save()

    def finish(self):
        try:
            self.recover('final restore')
            actual=d.config(self.c)
            changes={a:[v,actual[a]] for a,v in self.original.items() if v!=actual[a]}
            # 1830/1878 gateway+45 is PSC316StatusOkCount: a read-only counter.
            self.log['read_only_counter_changes']={a:v for a,v in changes.items() if int(a) in (1875,1923)}
            mismatch={a:v for a,v in changes.items() if int(a) not in (1875,1923)}
            self.log['configuration_mismatches']=mismatch
            assert not mismatch,mismatch
            self.log['final_snapshot']=d.snap(self.c)
            assert dep.POSTBOOT_STOPPED(self.log['final_snapshot'])
            self.log['restored']=True
        except BaseException:
            self.log['cleanup_error']=traceback.format_exc();raise
        finally:
            self.samples.close();self.root.destroy();self.stack.close();self.c.close()
            self.log['finished']=d.now();self.save()


def main():
    b=Bench()
    try:
        for repeat in (1,2):
            for point in POINTS:b.individual(point,repeat)
        b.recover('multi-cause baseline')
        for index,(name,ch,a,inp,fault) in enumerate(POINTS):
            b.wr(a,1-b.original[str(a)])
            mask=tuple(int(i<=index) for i in range(3))
            b.wait(f'concurrent faults add {name}',lambda z,m=mask:b.expected(z,m,1))
        for name,ch,a,inp,fault in POINTS:b.wr(a,b.original[str(a)])
        b.wait('all contacts normal retains three causes',lambda z:b.expected(z,(1,1,1),1)
            and all(z['values'][a]==0 for a in (1351,1354,1361)),hold=.8)
        b.reset();b.wait('one normal reset clears three causes',lambda z:b.expected(z,(0,0,0),0))
        b.log['sequence_completed']=True
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    b.log['passed']=b.log.get('sequence_completed',False) and b.log.get('restored',False)
    b.save();assert b.log['passed']
    print('BOARD DI PASS',len(b.log['checks']),'checks; baseline restored',flush=True)


if __name__=='__main__':main()
