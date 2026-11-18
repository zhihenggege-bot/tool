"""Two outdoor environment limits, input-only simulation, real60s gate."""
import full_queue_context_20261113 as ctx
from full_queue_context_20261113 import *
from bench_b01_ntc_20261111 import fixture
import math
import multiprocessing as mp
import queue
import struct

def run():
    b=current_bench_class()('R04_all_outdoor_environment_summary')
    e=b.log['regression']=dict(started=now(),scope='Two raw NTC0 input fixtures, software environment summary, actual real60s gate; BENCH compressor scheduling',samples=[],events=[])
    workers=[]
    try:
        b.setup(0)
        b.config({1343:1,1344:3,128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
                  160:250,161:250,120:20,412:1,416:100,417:1,418:0,315:0,
                  320:0,346:0,245:1,247:0,329:2,330:0,331:0,365:1,411:200,10:500,12:500})
        b.temperature(0,290);b.attach_extra()
        m=mp.get_context('spawn')
        for board,ss,sy in [(BOARDS[0],b.outss,b.outsy),b.extra[0]]:
            t=ss.target
            end=time.monotonic()+40
            while t.read16(sy['Parameter'][0]+330)!=1 or t.read16(sy['Parameter'][0]+332)!=3:
                assert time.monotonic()<end,'Shared type/fan not settled'
                time.sleep(.2)
            table=struct.unpack('<201f',bytes(t.read_memory_block8(sy['NTCtable'][0],804)))
            cal=signed16(t.read16(sy['Parameter'][0]+986));ss.close()
            if board==BOARDS[0]:b.outss=None
            values=m.Array('i',[-1]*8);stop=m.Event();stream=m.Queue()
            p=m.Process(target=fixture,args=(board,sy,values,stop,stream),daemon=True);p.start()
            workers.append((p,values,stop,stream,table,cal))
            kind,msg=stream.get(timeout=25);assert kind=='ready',(kind,msg)
        def settemp(unit,temp):
            p,values,stop,stream,table,cal=workers[unit-1]
            v=temp-cal;i=math.floor(v/10)+50;f=v/10-(i-50)
            r=table[i]+f*(table[i+1]-table[i]);raw=round(2.048*r/(5.1+r)/.0000625)
            with values.get_lock():values[0]=raw
            at=time.monotonic();e['events'].append(dict(at=now(),t=at,unit=unit,temp10=temp,raw=raw));b.save();return at
        def sample(after):
            result=[]
            for p,values,stop,stream,table,cal in workers:
                deadline=time.monotonic()+5
                while True:
                    assert time.monotonic()<deadline,'No fresh worker sample'
                    try:k,s=stream.get(timeout=1)
                    except queue.Empty:assert p.is_alive();continue
                    if k=='error':raise RuntimeError(s)
                    if k=='sample' and s['t']>=after and time.monotonic()-s['t']<1.5:result.append(s);break
            q=dict(at=now(),t=time.monotonic(),units=result,layers=b.rd(2598,2),summary=b.rd(737)[0],target=b.rd(881)[0])
            e['samples'].append(q);return q
        def wait(label,pred,seconds,after=None):
            begin=time.monotonic() if after is None else after;end=time.monotonic()+seconds;heartbeat=0
            while time.monotonic()<end:
                q=sample(begin)
                if pred(q):e[label]=q;b.save();print('ENV SUMMARY',label,q['layers'],q['summary'],flush=True);return q
                if time.monotonic()-heartbeat>=15:heartbeat=time.monotonic();b.save();print('ENV WAIT',label,q['layers'],q['summary'],flush=True)
            raise TimeoutError(label)
        settemp(1,200);settemp(2,200);b.reset_faults();b.start()
        wait('both_running',lambda q:all(s['output'][:2]==[1,1] for s in q['units']) and not any(q['layers']) and q['summary']==0,220)
        at=settemp(1,440)
        wait('one_blocked_summary_clear',lambda q:q['layers'][0]&32 and not(q['layers'][1]&32) and q['summary']==0 and q['units'][1]['output'][:2]==[1,1],100,at)
        at=settemp(2,440)
        wait('both_blocked_summary_asserted',lambda q:all(v&32 for v in q['layers']) and q['summary']==1 and all(s['output'][:2]==[0,0] for s in q['units']),100,at)
        at=settemp(1,200)
        wait('one_restored_summary_clear',lambda q:not(q['layers'][0]&32) and q['layers'][1]&32 and q['summary']==0,60,at)
        at=settemp(2,200)
        wait('both_environment_restored',lambda q:not any(v&32 for v in q['layers']) and q['summary']==0,60,at)
        e['verdict']='软件子范围通过';e['recovery_verified']=True;b.save()
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            for p,values,stop,stream,table,cal in workers:
                with values.get_lock():values[:]=[-1]*8
                stop.set();p.join(10)
                if p.is_alive():p.terminate();p.join(3);e['forced_fixture_exit']=True
                stream.close()
            if workers:
                b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
                b.outss.open();b.ot=b.outss.target
                if len(workers)>1:b.extra[0][1].open()
            b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

if __name__=='__main__':run()
