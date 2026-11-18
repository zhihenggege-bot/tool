"""Six outdoor fan pairs, driven exclusively by ordinary indoor run commands.

NTC0 acquisition input is held at 26 C so two fixed fans both participate.
Use a legal 90-second fan minimum stop to expose the gate despite the indoor
startup sequence. This is a BENCH software test, not physical relay timing.
"""
from joint_v1056_context_20261110 import *
from joint_outdoor_ntc_protection_20261110 import worker
import multiprocessing as mp
import struct,math,queue
CurrentBench=current_bench_class()


def main():
    b=CurrentBench('indoor_driven_six_fan_pairs');proc=None;stop=None;values=None
    e=dict(started=now(),status='running',pairs=[],
           scope='Normal 330[398] start/stop only; no direct outdoor demand writes. 316 NTC0 acquisition-input simulation at26C; 90s configured minimum stop; BENCH software edges, not terminals or production timing.')
    b.log['joint_fans']=e;b.save()
    def connect():
        if b.outss is None:
            b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            b.outss.open();b.ot=b.outss.target
    def end_worker():
        nonlocal proc
        if proc is not None:
            with values.get_lock():
                for i in range(8):values[i]=-1
            time.sleep(1);stop.set();proc.join(10)
            assert not proc.is_alive(),'fan input worker failed to stop'
            assert proc.exitcode==0,proc.exitcode
            proc=None;connect()
    def active(s,typ):
        o=s['output'];return [bool(o[2] or (o[7] if typ in (0,3) else 0)),bool(o[3])]
    def sample(r,label,issued=0):
        while True:
            try:kind,s=out.get(timeout=3)
            except queue.Empty:assert proc.is_alive(),'fan input worker exited';continue
            if kind=='error':raise RuntimeError(s)
            if kind!='sample':continue
            r.setdefault(label,[]).append(s)
            if s['t']>=issued:return s
    try:
        b.setup(0)
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,416:100,417:1,418:0,
            315:0,320:0,346:0,245:1,247:0,329:2,330:0,331:0,
            365:1,411:200,10:500,12:500,1331:150,1337:10,1338:90})
        b.temperature(0,290);b.reset_faults()
        for pos,(unit,typ) in enumerate(((0,0),(0,1),(1,2),(1,3),(2,2),(2,4))):
            r=dict(ids=[f'O-FANTIME-{pos*4+1:03d}'],unit_type=unit,fan_type=typ,started=now())
            e['pairs'].append(r);b.save()
            b.gateway(1830,unit);b.gateway(1831,typ)
            began=time.monotonic()
            while True:
                r['settings']={str(a):b.ot.read16(b.outsy['Parameter'][0]+2*a) for a in (107,165,166,179,180)}
                if r['settings']['179']==10 and r['settings']['180']==90:break
                assert time.monotonic()-began<45,('shared timing not propagated',r['settings'])
                time.sleep(.2)
            table=struct.unpack('<201f',bytes(b.ot.read_memory_block8(b.outsy['NTCtable'][0],804)))
            cal=signed16(b.ot.read16(b.outsy['Parameter'][0]+493*2))
            temp=260-cal;i=math.floor(temp/10)+50;fraction=temp/10-(i-50)
            resistance=table[i]+fraction*(table[i+1]-table[i])
            raw=round(2.048*resistance/(5.1+resistance)/.0000625)
            b.outss.close();b.outss=None
            ctx=mp.get_context('spawn');values=ctx.Array('i',[-1]*8);stop=ctx.Event();out=ctx.Queue()
            proc=ctx.Process(target=worker,args=(BOARDS[0],b.outsy,values,stop,out),daemon=True);proc.start()
            kind,_=out.get(timeout=30);assert kind=='ready'
            with values.get_lock():values[0]=raw
            r['raw_environment_input']=raw
            started=time.monotonic();b.start()
            r['indoor_started']=b.snapshot('indoor ordinary cooling startup, pair '+str((unit,typ)))
            first=None
            while True:
                s=sample(r,'initial_start',started);fans=active(s,typ)
                assert not any(s['alarms']),('initial fan test alarm',s)
                want=(all(fans) if (unit,typ)==(0,1) else any(fans))
                if want and s['params']['1425']==2 and s['params']['1426']==2:
                    first=s;break
                assert time.monotonic()-started<190,('indoor driven first start timeout',s)
            r['initial_both_compressors_cooling']=first
            # Stay running beyond the fan minimum run before requesting stop.
            hold=time.monotonic()
            while time.monotonic()-hold<11:s=sample(r,'initial_hold',hold)
            last_on=[None,None];off_edge=[None,None]
            for k,on in enumerate(active(s,typ)):
                if on:last_on[k]=s['t']
            issued=time.monotonic();b.wr(398,0)
            while True:
                s=sample(r,'normal_indoor_stop',issued);on=active(s,typ)
                for k in range(2):
                    if on[k]:last_on[k]=s['t'];off_edge[k]=None
                    elif last_on[k] is not None and off_edge[k] is None:off_edge[k]=s['t']
                if not any(on) and b.rd(709)[0]==0:break
                assert time.monotonic()-issued<100,('normal stop did not complete',s)
            assert any(t is not None for t in off_edge),('no same-fan stop edge',s)
            r['off_edges']=off_edge;r['stopped_indoor']=b.snapshot('stopped before ordinary indoor restart')
            restarted=time.monotonic();b.start()
            r['restart_indoor']=b.snapshot('ordinary indoor restart; outdoor fan gate must still apply')
            restarts={};request_seen=False
            while time.monotonic()-restarted<103:
                s=sample(r,'ordinary_restart',restarted);on=active(s,typ)
                if s['params']['1400'] or s['params']['1403']:request_seen=True
                for k in range(2):
                    if on[k] and off_edge[k] is not None and str(k) not in restarts:
                        dt=s['t']-off_edge[k];restarts[str(k)]=dt
                        assert dt>=89.5,('fan restarted before configured90s',k,dt,s)
                if all(str(k) in restarts for k,t in enumerate(off_edge) if t is not None):break
            assert request_seen and restarts,('restart request/edge missing',request_seen,restarts)
            assert all(str(k) in restarts for k,t in enumerate(off_edge) if t is not None),('some same-fan restarts not observed',off_edge,restarts)
            r.update(status='软件子范围通过：内机正常启停，同路风机遵守90秒停机设定',restart_off_seconds=restarts,finished=now());b.save()
            print('INDOOR-DRIVEN FAN PASS',unit,typ,restarts,flush=True)
            b.wr(398,0);issued=time.monotonic()
            while True:
                s=sample(r,'pair_final_stop',issued)
                if not any(active(s,typ)) and b.rd(709)[0]==0:break
                assert time.monotonic()-issued<100,('pair final stop',s)
            end_worker()
        e['status']='completed_six_pairs_ordinary_indoor_requests'
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0);end_worker();connect();b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

if __name__=='__main__':main()
