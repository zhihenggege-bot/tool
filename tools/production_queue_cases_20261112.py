"""Real-time PRODUCTION observations through normal commands and settings.

No control-state, output, fault or timer writes. Software output timing only.
Each timing result retains measured edges and unclosed scope explicitly.
"""
from production_queue_context_20261112 import *
from bench_remaining_outdoor_20261111 import HEAT
from continuous_special_stages_v1055_20261109 import paused
import argparse

def observe(b,row,label,predicate,timeout=600):
    end=time.monotonic()+timeout;heartbeat=0
    while True:
        paused();s=b.snapshot(label);s['t']=time.monotonic()
        if b.extra:
            s['direct_outputs']=[list(t.read_memory_block8(*sy['output'])) for t,sy in
                ((b.ot,b.outsy),(b.extra[0][1].target,b.extra[0][2]))]
        row.setdefault('samples',[]).append(s)
        if predicate(s):b.save();return s
        if time.monotonic()>end:raise TimeoutError(label)
        if time.monotonic()-heartbeat>=30:
            b.save();heartbeat=time.monotonic();print('PRODUCTION',label,s['state'][9],flush=True)
        time.sleep(.15)

def edge(rows,path,index,value):
    """Observed edge interval, not a claim of exact physical terminal time."""
    previous=None
    for s in rows:
        values=s
        for key in path:values=values[key]
        if values[index]==value:
            return dict(first_observed_s=s['t'],last_opposite_s=previous)
        previous=s['t']
    return None

def minimum_gap(first,second,required):
    if not first or not second:return dict(result='missing_edge',required_s=required)
    lower=second['last_opposite_s']-first['first_observed_s'] if second['last_opposite_s'] is not None else None
    upper=second['first_observed_s']-first['last_opposite_s'] if first['last_opposite_s'] is not None else None
    delta=second['first_observed_s']-first['first_observed_s']
    verdict='no_early_action_observed' if lower is not None and lower>=required else (
        'early_action_observed' if upper is not None and upper<required-1 else 'sampling_or_one_second_tick_boundary_review')
    return dict(required_s=required,observed_difference_s=delta,possible_interval_s=[lower,upper],result=verdict)

def compressor_edges(rows,value):
    events=[]
    for a,z in zip(rows,rows[1:]):
        for u in range(2):
            for c in range(2):
                if a['direct_outputs'][u][c]!=value and z['direct_outputs'][u][c]==value:
                    events.append(dict(unit=u+1,compressor=c+1,first_observed_s=z['t'],last_opposite_s=a['t']))
    return sorted(events,key=lambda e:e['first_observed_s'])

def run_sequence(mode=2,valves=False,exhaust=0,return_delay=0,return_present=False,ids=()):
    b=current_bench_class()(f'formal_sequence_m{mode}_v{int(valves)}_e{exhaust}_r{return_delay}_{int(return_present)}')
    e=b.log['formal_timing']=dict(ids=list(ids),mode=mode,valves=valves,exhaust_delay=exhaust,
        return_delay=return_delay,return_present=return_present,scope='PRODUCTION real wall time, ordinary no-thermal-load sequence; software relays/AO, physical contacts separate')
    try:
        b.setup(mode)
        b.config({128:0,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            329:2,330:2 if return_present else 0,331:1 if exhaust or return_present else 0,
            328:exhaust,132:return_delay,135:0,335:int(valves),336:int(valves),337:int(valves),338:int(valves),386:0})
        start=dict(samples=[]);e['start']=start
        start['samples'].append(dict(b.snapshot('before formal start'),t=time.monotonic()))
        start['command_before_t']=time.monotonic();b.wr(398,1);start['command_after_t']=time.monotonic()
        final=observe(b,start,'formal ordinary start',lambda s:s['state'][9]==2,420)
        start['supply_edge']=edge(start['samples'],['do'],3,1)
        start['return_edge']=edge(start['samples'],['do'],6,1) if return_present else None
        start['exhaust_edge']=edge(start['samples'],['do'],8,1) if exhaust or return_present else None
        delay=150 if valves else 10
        first=min((v for v in (start['supply_edge'],start['exhaust_edge']) if v),key=lambda v:v['first_observed_s'])
        command=dict(first_observed_s=start['command_after_t'],last_opposite_s=start['command_before_t'])
        start['valve_or_no_valve_wait']=minimum_gap(command,first,delay)
        if exhaust:
            a,z=(start['exhaust_edge'],start['supply_edge']) if exhaust>0 else (start['supply_edge'],start['exhaust_edge'])
            start['supply_exhaust_gap']=minimum_gap(a,z,abs(exhaust))
        if return_present:start['return_gap']=minimum_gap(start['supply_edge'],start['return_edge'],return_delay)
        assert not any(final['faults']),final
        stop=dict(samples=[]);e['stop']=stop
        stop['samples'].append(dict(b.snapshot('before formal stop'),t=time.monotonic()))
        stop['command_before_t']=time.monotonic();b.wr(398,0);stop['command_after_t']=time.monotonic()
        final=observe(b,stop,'formal ordinary stop',lambda s:s['state'][9]==0 and loads_off(s),900)
        for name,ch in (('supply',3),('return',6),('exhaust',8)):
            if name=='supply' or name=='return' and return_present or name=='exhaust' and (exhaust or return_present):
                stop[name+'_edge']=edge(stop['samples'],['do'],ch,0)
        if exhaust:
            a,z=(stop['supply_edge'],stop['exhaust_edge']) if exhaust>0 else (stop['exhaust_edge'],stop['supply_edge'])
            stop['reverse_supply_exhaust_gap']=minimum_gap(a,z,abs(exhaust))
        if return_present:stop['return_gap']=minimum_gap(stop['supply_edge'],stop['return_edge'],return_delay)
        e.update(executed=True,finished=now(),full_acceptance=False,
            remaining='Physical terminals; pressure-switch qualification/loaded shutdown not claimed by these no-load traces. See each measured timing interval.')
        b.save()
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:b.save();print('EVIDENCE',b.path,flush=True)

def run_loaded(humidifier=False,mode=1):
    b=current_bench_class()(f'formal_loaded_m{mode}_humid{int(humidifier)}')
    e=b.log['formal_timing']=dict(ids=(['T14-018'] if humidifier else ['T14-016','T14-019','T14-020','T14-021','T14-022','T14-023']) if mode==1 else ['T14-017' if humidifier else 'T14-015'],
        scope='Ordinary loaded demand; PRODUCTION wall clock; two316 software compressor/fan outputs; no physical loads')
    try:
        b.setup(mode);b.config(HEAT if mode else {**HEAT,127:0,416:100,417:1,418:0,411:200})
        b.config({125:int(humidifier),126:int(humidifier),248:int(humidifier),329:2,330:0,331:0,335:0,336:0,337:0,338:0})
        if humidifier:b.ai(1,300)
        b.temperature(0,220 if mode else 290);b.reset_faults();b.attach_extra()
        active=dict(samples=[]);e['initial_load']=active
        active['samples'].append(dict(b.snapshot('before load'),t=time.monotonic(),direct_outputs=[list(b.ot.read_memory_block8(*b.outsy['output'])),list(b.extra[0][1].target.read_memory_block8(*b.extra[0][2]['output']))]))
        b.wr(398,1)
        observe(b,active,'formal all four requested and active',lambda s:all(v==(3 if mode else 2) for q in s['outdoor_status'] for v in q),900)
        e['initial_loading_edges']=compressor_edges(active['samples'],1)
        e['loading30_observations']=[minimum_gap(a,z,30) for a,z in zip(e['initial_loading_edges'],e['initial_loading_edges'][1:])]
        if not humidifier and mode==1:
            # Request normal unload while the most recent compressor is still
            # below180s. Other interlocks may legitimately extend operation.
            b.temperature(0,280);b.config({127:0})
            unload=dict(samples=[active['samples'][-1]],requested_t=time.monotonic());e['normal_unload']=unload
            observe(b,unload,'formal ordinary unload',lambda s:all(v==0 for q in s['outdoor_status'] for v in q),900)
            e['unloading_edges']=compressor_edges(unload['samples'],0)
            e['unloading30_observations']=[minimum_gap(a,z,30) for a,z in zip(e['unloading_edges'],e['unloading_edges'][1:])]
            e['minimum_run_observations']=[]
            for u in range(2):
                for c in range(2):
                    a=edge(active['samples'],['direct_outputs',u],c,1)
                    z=edge(unload['samples'],['direct_outputs',u],c,0)
                    e['minimum_run_observations'].append(dict(unit=u+1,compressor=c+1,**minimum_gap(a,z,180)))
            b.temperature(0,220);b.config({127:1})
            reload=dict(samples=[unload['samples'][-1]],requested_t=time.monotonic());e['normal_reload']=reload
            observe(b,reload,'formal reload after real lockout',lambda s:all(v==3 for q in s['outdoor_status'] for v in q),900)
            e['minimum_stop_observations']=[]
            for u in range(2):
                for c in range(2):
                    a=edge(unload['samples'],['direct_outputs',u],c,0)
                    z=edge(reload['samples'],['direct_outputs',u],c,1)
                    e['minimum_stop_observations'].append(dict(unit=u+1,compressor=c+1,**minimum_gap(a,z,120)))
        stop=dict(samples=[],requested_t=time.monotonic());e['normal_stop']=stop;b.wr(398,0)
        observe(b,stop,'formal loaded normal stop',lambda s:s['state'][9]==0 and loads_off(s),900)
        e.update(executed=True,full_acceptance=False,finished=now(),remaining='Inspect requested/actual load and all measured edge intervals; physical terminal and full humidifier load acceptance separate')
        b.save()
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:b.save();print('EVIDENCE',b.path,flush=True)

def run_fan15():
    from bench_remaining_outdoor_20261111 import Inputs
    b=current_bench_class()('formal_two_fixed_fan15');inp=None
    e=b.log['formal_timing']=dict(ids=['T14-023'],samples=[],scope='PRODUCTION heat two-fixed fans, raw ambient input6.9C; software output edges, no contact instrumentation')
    try:
        b.setup(1);b.config(HEAT);b.gateway(1830,0);b.gateway(1831,1)
        b.config({1335:70,1336:50,1337:30,1338:30});b.temperature(0,220);b.reset_faults()
        inp=Inputs(b,e);inp.temperatures({0:69})
        e['samples'].append(inp.sample());b.wr(398,1);end=time.monotonic()+900
        both_since=None
        while True:
            paused();s=inp.sample();e['samples'].append(s)
            if s['output'][2] and s['output'][3]:
                if both_since is None:both_since=s['t']
                if s['t']-both_since>=3:break
            else:both_since=None
            assert time.monotonic()<end,'formal two-fixed fan start timeout'
        edges=[edge(e['samples'],['output'],c,1) for c in (2,3)]
        edges.sort(key=lambda e:e['first_observed_s'] if e else float('inf'))
        e['fan_edges']=edges;e['fan15_observation']=minimum_gap(*edges,15)
        e.update(executed=True,full_acceptance=False,remaining='One normal startup configuration; all configurations and physical relay gaps remain separately bounded')
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
        finally:b.finish();b.save();print('EVIDENCE',b.path,flush=True)

def run_fourway():
    from remaining529_manual_defrost_input_20261105 import manual_defrost
    b=current_bench_class()('formal_fourway_and_defrost60')
    e=b.log['formal_timing']=dict(ids=['O-FOURWAY-001','O-FOURWAY-002','T16-008'],runs=[],
        scope='PRODUCTION real clock, normal330 shared valve configuration and legacy HMI defrost INPUTS; outputs/state/timers read-only; software terminals only')
    try:
        for topology,seconds in ((0,20),(1,30),(1,120)):
            b.setup(1);b.config(HEAT);b.config({78:topology,41:seconds});b.temperature(0,220);b.reset_faults()
            row=dict(topology=topology,delay_seconds=seconds,samples=[]);e['runs'].append(row)
            b.attach_extra()
            row['samples'].append(dict(b.snapshot('before fourway load'),t=time.monotonic(),direct_outputs=[list(b.ot.read_memory_block8(*b.outsy['output'])),list(b.extra[0][1].target.read_memory_block8(*b.extra[0][2]['output']))]))
            b.wr(398,1)
            observe(b,row,'formal fourway heat delays',lambda s:all(q==[3,3] for q in s['outdoor_status']) and all(s['direct_outputs'][u][4] and (topology==0 or s['direct_outputs'][u][5]) for u in range(2)),900)
            row['effective_330_41']=b.rd(41)[0]
            row['effective_316_193']=b.ot.read16(b.outsy['Parameter'][0]+193*2)
            row['measured_delays']=[]
            for u in range(2):
                for c in range(2 if topology else 1):
                    a=edge(row['samples'],['direct_outputs',u],c,1)
                    z=edge(row['samples'],['direct_outputs',u],4+c,1)
                    row['measured_delays'].append(dict(unit=u+1,compressor=c+1,**minimum_gap(a,z,seconds)))
            if topology==1 and seconds==30:
                manual_defrost(b,True,session=b.extra[1][1])
                active=dict(samples=[]);row['defrost']=active
                observe(b,active,'formal active defrost',lambda s:b.rd(1550,2)==[8,8] and s['direct_outputs'][0][:2]==[1,1],180)
                manual_defrost(b,False,session=b.extra[1][1])
                recovery=dict(samples=[]);row['defrost_recovery']=recovery
                begin=None
                def complete(s):
                    nonlocal begin
                    phase=b.rd(1550,2);s['phase']=phase
                    if phase==[7,7] and begin is None:begin=s['t']
                    if begin is not None and phase==[0,0]:
                        recovery['observed_recovery_seconds']=s['t']-begin
                        return True
                    return False
                observe(b,recovery,'formal defrost recovery60',complete,200)
            b.stop()
            for _,ss,_ in b.extra:ss.close()
            b.extra=[]
            row['finished']=now();b.save()
        e.update(executed=True,full_acceptance=False,finished=now(),remaining='Reverse compressor start order and fault-isolation valve branches still separate; recovery uses330 mirror interval, direct fine-grained phase timing should be reviewed')
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:b.save();print('EVIDENCE',b.path,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('sequence','loaded','fourway'));p.add_argument('--mode',type=int,default=2)
    p.add_argument('--valves',action='store_true');p.add_argument('--exhaust',type=int,default=0);p.add_argument('--return-delay',type=int,default=0)
    p.add_argument('--return-present',action='store_true');p.add_argument('--humidifier',action='store_true');p.add_argument('--ids',nargs='*',default=[])
    a=p.parse_args()
    if a.action=='sequence':run_sequence(a.mode,a.valves,a.exhaust,a.return_delay,a.return_present,a.ids)
    elif a.action=='loaded':run_loaded(a.humidifier,a.mode)
    else:run_fourway()
