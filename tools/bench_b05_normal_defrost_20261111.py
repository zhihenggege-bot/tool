"""Natural 316 defrost qualification and two independent fin-temperature exits."""
from joint_v1058_context_20261111 import *
from joint_timed_defrost_20261110 import worker
import multiprocessing as mp
import math
import queue


def fixture(board,sy,values,stop,out):
    out.cancel_join_thread()
    worker(board,sy,values,stop,out)


def run():
    b=current_bench_class()('B05_natural_defrost')
    e=b.log['defrost_natural']=dict(events={},samples=[],scope='1# natural 15-minute interval, healthy NTC0/1/2 input simulation; 330 heating request and permit; BENCH recovery only')
    proc=None
    try:
        assert b.rd(398)==b.rd(709)==[0] and not any(b.rd(2598,2))
        b.setup(1)
        b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,
                  315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,
                  428:0,347:100,348:1,349:0,346:0,320:0,245:1,247:0,
                  329:2,330:0,331:0,365:1,372:350,10:500,12:500,
                  1392:5,1393:65516,1394:100,1395:15,1397:400,1398:4})
        b.temperature(0,220)
        e['settings']={str(a):b.ot.read16(b.outsy['Parameter'][0]+a*2) for a in range(185,193)}
        cal=[signed16(b.ot.read16(b.outsy['Parameter'][0]+2*(493-i))) for i in range(3)]
        b.attach_extra(); _,indoor,isy=b.extra[1]
        b.outss.close();b.outss=None
        ctx=mp.get_context('spawn');values=ctx.Array('i',[-1]*8);stop=ctx.Event();stream=ctx.Queue()
        proc=ctx.Process(target=fixture,args=(BOARDS[0],b.outsy,values,stop,stream),daemon=True);proc.start()
        kind,ready=stream.get(timeout=25);assert kind=='ready',(kind,ready)
        table=ready['table']

        def set_temps(*temps):
            raw=[]
            for i,temp in enumerate(temps):
                v=temp-cal[i];j=math.floor(v/10)+50;f=v/10-(j-50)
                resistance=table[j]+f*(table[j+1]-table[j])
                raw.append(round(2.048*resistance/(5.1+resistance)/.0000625))
            with values.get_lock():values[:3]=raw
            row=dict(at=now(),t=time.monotonic(),temps10=temps,raw=raw)
            e.setdefault('inputs',[]).append(row);b.save();return row['t']

        def until(label,seconds,predicate):
            end=time.monotonic()+seconds;heartbeat=0
            while time.monotonic()<end:
                try:kind,s=stream.get(timeout=2)
                except queue.Empty:
                    if not proc.is_alive():raise RuntimeError('input worker exited')
                    continue
                if kind=='error':raise RuntimeError(s)
                if kind!='diagnostic' or time.monotonic()-s['t']>2:continue
                s.update(owner=indoor.target.read8(isy['PSC316DefrostOwner'][0]),
                         mirrors=[b.rd(1550,2),b.rd(1620,2)],fin330=b.rd(1561,2),other=b.rd(1625,2))
                e['samples'].append(s)
                if predicate(s):e['events'][label]=s;b.save();return s
                if time.monotonic()-heartbeat>30:
                    heartbeat=time.monotonic();b.save()
                    print('DEFROST',label,s.get('DefGapCount'),s['mirrors'],flush=True)
            raise TimeoutError(label)

        set_temps(50,-60,100)
        b.start()
        until('heating_both',170,lambda s:s['output'][:2]==[1,1] and s['other']==[3,3])
        active=until('active_natural',1020,lambda s:[s['params'][str(a)] for a in (1420,1421)]==[8,8]
                     and s['output'][:2]==[1,1] and s['owner']==1)
        e['fan_valve_off']=not any(active['output'][i] for i in (2,3,4,5,7))
        e['peer_did_not_enter']=not any(8 in s['mirrors'][1] for s in e['samples'])
        first=set_temps(50,410,100)
        until('first_fin_exits_only_its_system',30,lambda s:s['t']>=first and s['output'][:2]==[0,1])
        second=set_temps(50,410,410)
        recovered=until('second_fin_ends_defrost',30,lambda s:s['t']>=second and s['output'][:2]==[0,0]
                        and all(s['params'][str(a)]==7 for a in (1420,1421)))
        idle=until('both_clear_after_bench_recovery',30,lambda s:s['owner']==0 and s['mirrors'][0]==[0,0])
        e.update(software_scope_passed=True,recovery_to_owner_clear_s=idle['t']-recovered['t'])
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if proc is not None:
                with values.get_lock():values[:]=[-1]*8
                stop.set();proc.join(8)
                if proc.is_alive():proc.terminate();proc.join(3)
                e['fixture_exitcode']=proc.exitcode;stream.close()
        finally:
            try:
                if b.outss is None:
                    b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
                        options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
                    b.outss.open();b.ot=b.outss.target
                b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
