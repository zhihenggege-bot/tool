"""Retest all14 PSC330 inputs using the user's CURRENT polarity baseline.

Only Modbus configuration/start/stop/reset and polarity stimuli. SWD read-only.
Production time gates are never changed. Individual failures remain in report.
"""
import json
import struct
import time
import traceback
from pathlib import Path
import board_fan_DI_v1076_20261124 as base

dep,d=base.dep,base.d
DAY=dep.R/'测试证据/全部DI当前极性复测_V1076_20261124'
NAMES=('00','01','02','03','04','05','06','07','10','11','12','13','14','15')
POLARITY=(155,156,157,158,159,389,390,391,392,393,394,395,396,397)
FAULT=(911,960,None,601,962,909,966,968,910,956,958,964,913,912)


class Bench(base.Bench):
    def __init__(self):
        base.DAY=DAY
        super().__init__()
        self.log['scope']='All14 current-polarity inputs; Modbus polarity simulation; ventilation; real production timing; SWD read-only'
        self.log['polarity_baseline']={f'X{ch}':self.original[str(a)] for ch,a in zip(NAMES,POLARITY)}
        self.log['cases']=[];self.log['covered']=[];self.log['failures']=[]
        self.save()

    def sample(self,label):
        began=time.monotonic();v={}
        for a,n in ((594,54),(700,15),(814,8),(861,1),(888,2),(909,16),(956,13),(1350,24)):
            v.update({a+i:x for i,x in enumerate(self.rd(a,n))})
        raw=list(self.t.read_memory_block8(self.sym['input'],14))
        adjusted={'X_'+ch:self.t.read8(self.sym['X_'+ch]) for ch in NAMES}
        out=list(self.t.read_memory_block8(self.sym['output'],16))
        da=list(struct.unpack('<10H',bytes(self.t.read_memory_block8(self.sym['DA'],20))))
        outdoor=[]
        for t in self.targets[:2]:
            pb,pd=t.read32(0x40010c0c),t.read32(0x4001140c)
            outdoor.append([(pb>>(12+i))&1 for i in range(4)]+[(pd>>(8+i))&1 for i in range(4)])
        z=dict(at=d.now(),t=began,read_ended=time.monotonic(),label=label,values=v,
            raw_input=raw,adjusted=adjusted,indoor_output=out,da=da,outdoor_gpio=outdoor,
            remote_stop=self.t.read8(self.sym['RemoteInterlockStopFlag']))
        self.samples.write(json.dumps(z,ensure_ascii=False,separators=(',',':'))+'\n')
        keys=set(a for a in FAULT if a is not None)|{605,709,710,819,861,924,1366,817,820}
        edges={str(a):v[a] for a in keys if self.previous is None or self.previous['values'][a]!=v[a]}
        if edges:self.log['events'].append(dict(at=z['at'],t=began,label=label,edges=edges));self.save()
        self.previous=z
        assert not any(g[i] for g in outdoor for i in (0,1)),('Unexpected compressor output',z)
        assert not any(v[a] for a in range(594,627) if a not in (601,605)),('Unexpected unrelated indoor fault',z)
        if began-self.last_notice>20:
            print('TRACE',label,'step',v[709],'fans',[out[i] for i in (3,6,8)],
                'faults',{a:v[a] for a in FAULT if a is not None and v[a]},'Y05',v[819],flush=True)
            self.last_notice=began
        return z

    def wait(self,label,predicate,timeout=20,hold=.3):
        began=time.monotonic();first=None
        while True:
            z=self.sample(label)
            if predicate(z):
                if first is None:first=z
                if z['t']-first['t']>=hold:
                    self.check(label,True,elapsed_s=time.monotonic()-began,first=first,last=z)
                    return first
            else:first=None
            if time.monotonic()-began>timeout:self.check(label,False,last=z,timeout=timeout)
            time.sleep(.08)

    def contact(self,ch,desired):
        idx=NAMES.index(ch);reg=POLARITY[idx]
        raw=self.t.read8(self.sym['input']+idx)
        polarity=int(raw==desired)
        began=time.monotonic();self.config({reg:polarity})
        self.wait(f'X{ch} adjusted input={desired}',lambda z:z['adjusted']['X_'+ch]==desired,timeout=4,hold=0)
        return began

    @staticmethod
    def clear(z):
        return not any(z['values'][a] for a in set(a for a in FAULT if a is not None)|{605,710,819,861,924})

    def healthy(self):
        for ch in NAMES:self.contact(ch,int(ch in ('14','15')))
        self.wait('all fault inputs normal after filtering',lambda z:all(z['values'][1350+i]==0
            for i,ch in enumerate(NAMES) if ch not in ('14','15')),timeout=5)
        self.reset();self.wait('all independent faults and Y05 clear',self.clear)

    def setup(self,**kwargs):
        super().setup(**kwargs)
        self.config({328:0})  # configured fan stagger only; protection60/10 unchanged

    def generic(self,ch,stop,delay=3):
        fault=FAULT[NAMES.index(ch)]
        self.setup(return_mode=1,exhaust_mode=1)
        self.start(f'X{ch} normal ventilation running')
        short=5 if ch=='05' else 1
        self.contact(ch,1)
        self.observe(f'X{ch} short{short}s input no alarm',short,lambda z:z['values'][fault]==0)
        self.contact(ch,0)
        self.observe(f'X{ch} interrupted input no alarm',.5,lambda z:z['values'][fault]==0)
        began=self.contact(ch,1)
        z=self.wait(f'X{ch} confirms independent fault{fault}',lambda z:z['values'][fault]==1
            and z['values'][819]==z['values'][861]==1,timeout=delay+5,hold=.3)
        self.log.setdefault('timings',[]).append(dict(test=f'X{ch} fault{fault}',
            input_write_t=began,first_confirmed_t=z['t'],observed_delay_s=z['t']-began))
        if stop:
            self.wr(398,0)
            self.wait(f'X{ch} protective fan stop',lambda z:z['values'][710]==1 and z['values'][709]==0
                and not any(z['indoor_output'][i] for i in (3,6,8)),timeout=65)
        else:
            self.observe(f'X{ch} alarm does not stop ventilation fans',1,
                lambda z:z['values'][709]==2 and all(z['indoor_output'][i] for i in (3,6,8)))
        self.contact(ch,0)
        self.wait(f'X{ch} filtered input normal',lambda z:z['values'][1350+NAMES.index(ch)]==0)
        self.observe(f'X{ch} recovered input retains alarm until reset',.6,lambda z:z['values'][fault]==1)
        self.reset();self.wait(f'X{ch} healthy reset clears fault',lambda z:z['values'][fault]==0 and z['values'][819]==0)
        self.stop(f'X{ch} final stop')

    def remote(self):
        self.setup(return_mode=1,exhaust_mode=0)
        self.start('X02 local-mode ventilation start')
        self.contact('02',1)
        self.observe('X02 local mode ignores signal1',3.4,lambda z:z['values'][709]==2 and self.clear(z))
        self.contact('02',0)
        self.observe('X02 local mode ignores signal0',3.4,lambda z:z['values'][709]==2 and self.clear(z))
        self.stop('X02 stop before remote selection')
        self.config({163:1})
        self.wait('X02 remote selected without request stays stopped',lambda z:z['values'][709]==0 and self.clear(z),hold=1)
        self.contact('02',1)
        self.wait('X02 remote request starts unit',lambda z:z['values'][709]==2 and self.clear(z),timeout=30)
        self.contact('02',0)
        self.observe('X02 short remote stop request ignored',1,lambda z:z['values'][709]==2 and self.clear(z))
        self.contact('02',1)
        self.observe('X02 interrupted remote stop request recovers',.7,lambda z:z['values'][709]==2 and self.clear(z))
        began=self.contact('02',0)
        self.wait('X02 remote stop qualification3s',lambda z:z['remote_stop']==1 and z['values'][709]!=2,timeout=7,hold=0)
        self.wait('X02 remote stop finishes without alarm',lambda z:z['values'][709]==0 and self.clear(z)
            and not any(z['indoor_output'][i] for i in (3,6,8)),timeout=60)
        self.contact('02',1)
        self.wait('X02 reconnect automatically restarts',lambda z:z['values'][709]==2 and self.clear(z),timeout=35)
        self.contact('02',0)
        self.wait('X02 release before returning local',lambda z:z['values'][709]==0 and self.clear(z),timeout=65)
        self.config({163:0});self.wr(398,0)

    def finish(self):
        try:
            # A pending remote run request must be removed before normal stop.
            if self.rd(163)==[1]:self.contact('02',0);self.config({163:0})
            self.stop('final normal stop');self.healthy()
            for a in sorted(self.touched-{236}):self.wr(a,self.original[str(a)])
            if 236 in self.touched:self.wr(236,self.original['236'])
            self.wait('user baseline restored and all faults clear',lambda z:z['values'][709]==0 and self.clear(z),timeout=15)
            actual=d.config(self.c)
            changes={a:[v,actual[a]] for a,v in self.original.items() if v!=actual[a]}
            self.log['readonly_counter_changes']={a:v for a,v in changes.items() if int(a) in (1875,1923)}
            self.log['configuration_mismatches']={a:v for a,v in changes.items() if int(a) not in (1875,1923)}
            assert not self.log['configuration_mismatches'],self.log['configuration_mismatches']
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
    tasks=[(ch,lambda c=ch:b.generic(c,True)) for ch in ('00','01','03','04','13')]
    tasks += [('05',lambda:b.generic('05',False,15))]
    tasks += [(ch,lambda c=ch:b.generic(c,False)) for ch in ('06','07','10')]
    tasks += [('02',b.remote),('11',lambda:b.overload('11')),
              ('12',lambda:b.overload('12',2)),('15',lambda:b.pressure('15',1)),('14',lambda:b.pressure('14',2))]
    try:
        for ch,fn in tasks:
            row=dict(input='X'+ch,started=d.now(),passed=False);b.log['cases'].append(row);b.save()
            try:
                fn();row['passed']=True;b.log['covered'].append('X'+ch)
            except BaseException:
                row['error']=traceback.format_exc();b.log['failures'].append(row.copy());b.save()
                print('CASE FAILED X'+ch,row['error'],flush=True)
                # Keep evidence and proceed if ordinary recovery succeeds.
                if b.rd(163)==[1]:b.contact('02',0);b.config({163:0})
                b.wr(398,0);b.healthy();b.stop('recovery after failed case')
            row['finished']=d.now();b.save()
        b.log['sequence_completed']=True
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    b.log['passed']=len(b.log['covered'])==14 and not b.log['failures'] and b.log.get('restored',False)
    b.save()
    print('ALL DI COMPLETE',len(b.log['covered']),'/14;checks',len(b.log['checks']),
        'failures',len(b.log['failures']),'restored',b.log.get('restored'),flush=True)


if __name__=='__main__':main()
