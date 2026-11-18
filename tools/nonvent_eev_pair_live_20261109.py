"""Paired indoor/outdoor EEV mode check; genuine commands, read-only SWD.

The first installed outdoor unit and its two indoor circuits are observed.
This establishes software steps, not motor pulses or mechanical valve position.
"""
from v1055_bench_context_20261109 import *
from nonvent_defrost_v1055_20261109 import DefrostBench, paused
import struct


class PairedBench(DefrostBench):
    def gateway(self,a,value):
        try:super().gateway(a,value)
        except AssertionError as exc:
            if 'destination mismatch' not in str(exc):raise
            target=165+(a-1830)%48;began=time.monotonic();samples=[]
            while True:
                destination=signed16(self.ot.read16(self.outsy['Parameter'][0]+target*2))
                samples.append(dict(at=now(),value=destination))
                if destination==value:break
                assert time.monotonic()-began<45,('destination confirmation timeout',a,value,destination)
                time.sleep(.2)
            self.log.setdefault('gateway_async_confirmation',[]).append(dict(address=a,expected=value,samples=samples));self.save()


def run(mode):
    b=PairedBench('paired_eev_mode_'+str(mode));cid='T12-001' if mode==0 else 'T12-002'
    e=dict(passed=False,mode=mode,trace=[],initial_seen=[False,False],
        scope='First installed outdoor unit, two paired circuits; normal real scheduling; software positions only')
    b.log['cases'][cid]=e;b.save()
    try:
        b.swd=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        b.swd.open();t=b.swd.target
        b.setup(mode)
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,416:100,417:1,418:0,
            426:100,427:1,428:0,315:0,320:0,346:0,245:1,247:0,
            329:2,330:0,331:0,365:1,366:50,367:50,368:1,369:1000,
            370:0,16:10,411:200,371:20,10:500,12:500})
        for a,v in ((1865,1),(1866,200),(1867,50),(1868,10)):
            b.gateway(a,v)
        b.temperature(0,290 if mode==0 else 220);b.reset_faults()
        def read():
            return dict(t=time.monotonic(),at=now(),
                indoor=list(struct.unpack('<16h',bytes(t.read_memory_block8(b.sy['Parameter'][0]+1145*2,32)))),
                indoor_valid=list(t.read_memory_block8(b.sy['EEVSpecValidSamples'][0],4)),
                outdoor=list(struct.unpack('<8h',bytes(b.ot.read_memory_block8(b.outsy['Parameter'][0]+805*2,16)))),
                outdoor_valid=list(b.ot.read_memory_block8(b.outsy['EEVSpecValidSamples'][0],2)),
                comp=list(b.ot.read_memory_block8(b.outsy['Comp'][0],2)))
        before=read();e['before']=before
        # Outdoor channels 3/4 are uninstalled driver slots and retain their
        # boot seating values; qualify only the two paired installed valves.
        assert all(v==0 for v in before['indoor']) and all(before['outdoor'][i]==0 for i in (0,1,4,5)),before
        b.wr(398,1);began=time.monotonic();heartbeat=began;full_at=None;last=None
        while True:
            paused();s=read();e['trace'].append(s)
            for i in range(2):
                if mode==0:
                    if s['indoor'][i]==s['indoor'][8+i]==200 and s['indoor_valid'][i]==0:e['initial_seen'][i]=True
                    assert s['outdoor'][i]==s['outdoor'][4+i]==0,('outdoor valve open during cooling',s)
                else:
                    assert s['indoor'][i]==s['indoor'][8+i]==0,('indoor valve open during ordinary heating',s)
                    if s['outdoor'][i]==s['outdoor'][4+i]==200 and s['outdoor_valid'][i]==0:e['initial_seen'][i]=True
            if time.monotonic()-heartbeat>=15:
                z=b.sample('paired valve mode status');e.setdefault('snapshots',[]).append(z)
                assert not any(z['faults']),z
                print('PAIRED EEV',mode,round(time.monotonic()-began,1),s['comp'],s['indoor'][:2],s['indoor'][8:10],s['outdoor'][:2],s['outdoor'][4:6],e['initial_seen'],flush=True)
                heartbeat=time.monotonic();b.save()
            if s['comp']==[1,1] and all(e['initial_seen']):
                if full_at is None:full_at=time.monotonic()
                if time.monotonic()-full_at>=12 and (mode==0 or all(v==2 for v in s['outdoor_valid'])):break
            assert time.monotonic()-began<300,('paired startup or PID history not observed',s,e['initial_seen'])
            time.sleep(.06)
        e['running']=b.sample('paired mode running confirmed')
        expected=2 if mode==0 else 3
        assert e['running']['outdoor_status'][0]==[expected,expected],e['running']
        if mode==1:
            e['pid_history_established']=all(v==2 for v in s['outdoor_valid'])
            assert e['pid_history_established'],s
        e['passed']=True;b.save()
        text=('V10.55/V12.39，正常'+('制冷' if mode==0 else '热泵制热')+
            '启动，第一块外机两回路逐个实际运行；'+
            ('内阀目标和软件实际步数均采到起始200且历史为0，运行期间外阀目标/软件实际均0。' if mode==0 else
             '内阀目标/软件实际始终0，外阀两路采到起始200且历史为0，后续真实PID历史建立为2。')+
            '两压机运行及起始确认后继续观察12s；只读SWD，无阀位/PID/输出注入。仅第一块外机的两配对回路，脉冲/机械/正式档另验。')
        b.record_local(cid,True,text,e)
        records=json.loads(RESULTS.read_text('utf8'));records[cid]['inputs']='Normal on/off, legal room calibration, normal 330->316 gateway EEV settings; all EEV state read-only';dump(RESULTS,records)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:b.finish()


if __name__=='__main__':
    import sys
    run(int(sys.argv[1]))
