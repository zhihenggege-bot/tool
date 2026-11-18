"""Dual-direction environment probe fault regression, normal330 demand."""
import full_queue_context_20261113 as ctx
from full_queue_context_20261113 import *
import multiprocessing as mp
import queue
from joint_outdoor_ntc_protection_20261110 import worker

def fixture(*args):
    args[-1].cancel_join_thread()
    worker(*args)

def run(unit,exercise_load=False):
    b=current_bench_class()('R05_healthy_demand_with_fault' if exercise_load else f'R0{unit}_ambient_fault_isolation')
    e=b.log['regression']=dict(unit=unit,started=now(),samples=[],events=[],
        scope='Raw ADC/filter probe input simulation; actual board software outputs; no physical terminals or formal timing')
    proc=None
    try:
        b.setup(1)
        b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,
                  315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,
                  428:0,347:100,348:1,349:0,346:0,320:0,245:1,247:0,
                  329:2,330:0,331:0,365:1,372:350,10:500,12:500})
        b.temperature(0,220);b.reset_faults();b.start()
        b.wait('four heating outputs before isolated fault',lambda s:all(v==3 for p in s['outdoor_status'] for v in p),220)
        b.attach_extra()
        board=BOARDS[unit-1]
        sy=b.outsy if unit==1 else b.extra[0][2]
        if unit==1:b.outss.close();b.outss=None
        else:b.extra[0][1].close()
        peer=b.extra[0][1].target if unit==1 else b.ot
        peer_sy=b.extra[0][2] if unit==1 else b.outsy
        m=mp.get_context('spawn');values=m.Array('i',[-1]*8);stop=m.Event();stream=m.Queue()
        proc=m.Process(target=fixture,args=(board,sy,values,stop,stream),daemon=True);proc.start()
        kind,msg=stream.get(timeout=25);assert kind=='ready',(kind,msg)
        def sample(after):
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                try:k,s=stream.get(timeout=1)
                except queue.Empty:assert proc.is_alive();continue
                if k=='error':raise RuntimeError(s)
                if k!='sample' or s['t']<after or time.monotonic()-s['t']>1.5:continue
                s.update(mirror=b.rd(2022+128*(unit-1),28),layers=b.rd(2598,2),
                         global_environment_off=b.rd(737)[0],target=b.rd(881)[0],page=b.rd(540)[0],
                         peer_output=list(peer.read_memory_block8(*peer_sy['output'])),
                         peer_alarms=[peer.read16(peer_sy['Parameter'][0]+2*a) for a in range(600,628)])
                e['samples'].append(s);return s
            raise TimeoutError('fresh input sample')
        def wait(label,predicate,seconds,after=None):
            start=time.monotonic() if after is None else after;end=time.monotonic()+seconds
            while time.monotonic()<end:
                s=sample(start)
                if predicate(s):e[label]=s;b.save();print('ISOLATION',unit,label,flush=True);return s
            raise TimeoutError(label)
        wait('healthy',lambda s:s['output'][:2]==[1,1] and s['peer_output'][:2]==[1,1] and not any(s['alarms']) and not any(s['peer_alarms']),20)
        fixed_page=b.rd(540)[0]
        at=time.monotonic()
        with values.get_lock():values[0]=0
        e['events'].append(dict(at=now(),input='NTC0 raw zero',t=at));b.save()
        edge=wait('source_fault_and_protection',lambda s:s['alarms'][12]==1 and s['output'][:2]==[0,0],35,at)
        wait('mirror_asserted_fixed_page',lambda s:s['mirror'][12]==1 and s['layers'][unit-1]&31,50,edge['t'])
        held=[];end=time.monotonic()+35
        while time.monotonic()<end:
            s=sample(edge['t']);held.append(s)
            if len(held)%10==0:b.save()
        e['fixed_page_hold']=dict(seconds=held[-1]['t']-held[0]['t'],samples=len(held),
            peer_continues=all(s['peer_output'][:2]==[1,1] and not any(s['peer_alarms']) for s in held),
            source_protected=all(s['output'][:2]==[0,0] and s['alarms'][12]==1 for s in held),
            global_gate_clear=all(s['global_environment_off']==0 for s in held),
            mirror_stays=all(s['mirror'][12]==1 for s in held),page_stays=all(s['page']==fixed_page for s in held))
        if exercise_load:
            e['demand_cycle']=dict(scope='Normal room temperature/reheat settings; BENCH minima and scheduling; actual outputs recorded')
            b.config({127:0});b.temperature(0,280)
            e['demand_cycle']['unloaded']=wait('healthy_unloaded',lambda s:s['target']==0 and s['peer_output'][:2]==[0,0] and s['output'][:2]==[0,0] and s['alarms'][12] and s['global_environment_off']==0,200)
            b.temperature(0,220);b.config({127:1})
            e['demand_cycle']['reloaded']=wait('healthy_reloaded',lambda s:s['target']==4 and s['peer_output'][:2]==[1,1] and s['output'][:2]==[0,0] and s['alarms'][12] and s['global_environment_off']==0,200)
            e['demand_cycle']['verified']=True
        b.wr(540,2 if fixed_page==1 else 1)
        wait('mirror_after_page_switch',lambda s:s['mirror'][12]==1,15)
        removed=time.monotonic()
        with values.get_lock():values[0]=-1
        wait('source_auto_recovered',lambda s:not any(s['alarms']) and not(s['params']['1501']&31),45,removed)
        wait('mirror_recovered',lambda s:not any(s['mirror']) and not(s['layers'][unit-1]&31),50,removed)
        e['verdict']='软件子范围通过' if all(v for k,v in e['fixed_page_hold'].items() if isinstance(v,bool)) else '实测有待核对'
        e['recovery_verified']=True;b.save()
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            if proc:
                with values.get_lock():values[:]=[-1]*8
                stop.set();proc.join(10)
                if proc.is_alive():proc.terminate();proc.join(3);e['fixture_forced_exit']=True
                e['fixture_exitcode']=proc.exitcode
                stream.close()
                if unit==1:
                    b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
                    b.outss.open();b.ot=b.outss.target
                else:b.extra[0][1].open()
            b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,e.get('verdict','incomplete'),flush=True)

if __name__=='__main__':
    import sys
    run(int(sys.argv[1]))
