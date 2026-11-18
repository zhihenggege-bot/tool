"""Six fan types through ordinary330 operator inputs, never316 demand writes."""
from bench_remaining_outdoor_20261111 import *


def run(minimum_seconds=30, pairs=None, initial_hold_seconds=11, require_both=False, independent_spotcheck=False):
    assert isinstance(minimum_seconds,int) and 10<=minimum_seconds<=300
    selected_pairs=PAIRS if pairs is None else pairs
    assert selected_pairs and all(pair in PAIRS for pair in selected_pairs)
    assert initial_hold_seconds>=0
    assert not independent_spotcheck or (tuple(selected_pairs)==((2,4),) and require_both and initial_hold_seconds==0)
    spotcheck_pause=ROOT/'.codex-tmp/fan_minrun_spotcheck_pause.request'
    def check_spotcheck_pause():
        if spotcheck_pause.exists():raise InterruptedError('Minimum-run spotcheck paused; normal cleanup follows')
    (check_spotcheck_pause if independent_spotcheck else paused)()
    b=current_bench_class()('remaining_normal_prestart_six_pairs_'+str(minimum_seconds));inp=None
    if independent_spotcheck:
        # Explicit, user-authorized single-configuration scope. The main
        # controller's pause marker remains intact; this scope has its own stop.
        b.input_pause_check=check_spotcheck_pause
    e=b.log['remaining_functional']=dict(kind='normal_prestart_'+str(minimum_seconds),cases=[],pairs=[],minimum_seconds=minimum_seconds,
        scope='Normal330 start/stop and temperature-control settings, raw316 ambient INPUT; actual software output edges; no316 request/demand/state writes; BENCH, no physical terminals or formal15s acceptance')
    e.update(initial_hold_seconds=initial_hold_seconds,require_both=require_both,
        timing_acceptance='Raw observed differences; legacy .5s assertion is a diagnostic, not user-approved tolerance for all settings')
    e['pause_scope']=str(spotcheck_pause.relative_to(ROOT)) if independent_spotcheck else 'main_queue'

    def fans(s,typ):
        o=s['output']
        return [bool(o[2] or (o[7] if typ==0 else 0)),
                bool(o[3] or (o[7] if typ==3 else 0))]

    def wait(row,label,typ,predicate,seconds):
        end=time.monotonic()+seconds;heartbeat=0
        while time.monotonic()<end:
            s=inp.sample();s.update(target330=b.rd(881)[0],other330=b.rd(1625,2),actual_count330=b.rd(119)[0],environment330=b.rd(882)[0]);row.setdefault(label,[]).append(s)
            assert not any(s['alarms']),('healthy fan precondition lost',s)
            if predicate(s):b.save();return s
            if time.monotonic()-heartbeat>25:
                heartbeat=time.monotonic();b.save()
                print('NORMAL PRESTART',row['pair'],label,s['output'][:4],flush=True)
        raise TimeoutError(label)

    try:
        b.setup(1);b.config(HEAT);b.config({1335:70,1336:50,1337:minimum_seconds,1338:minimum_seconds})
        b.temperature(0,220);b.reset_faults()
        inp=Inputs(b,e);inp.temperatures({0:69})
        for pair in selected_pairs:
            index=PAIRS.index(pair)
            row=dict(pair=pair,started=now());e['pairs'].append(row)
            try:
                b.wr(398,0)
                wait(row,'before_off',pair[1],lambda s:not any(s['output'][i] for i in (0,1,2,3,7)),minimum_seconds+220)
                # Shared165/166 accepts changes only after330 SysStep==0.
                # Outdoor relays can already be off during indoor rundown.
                b.stop()
                inp.close();inp=None
                b.gateway(1830,pair[0]);b.gateway(1831,pair[1])
                inp=Inputs(b,e);inp.temperatures({0:69})
                b.temperature(0,220);b.config({127:1});b.wr(398,1)
                first=wait(row,'initial_start',pair[1],lambda s:(all if require_both else any)(fans(s,pair[1])),minimum_seconds+210)
                end=time.monotonic()+initial_hold_seconds
                while time.monotonic()<end:row.setdefault('initial_run',[]).append(inp.sample())
                # Ordinary330 controller unloads; it alone owns316 requests.
                b.config({127:0});b.temperature(0,280)
                last=wait(row,'normal_unload',pair[1],lambda s:not any(s['output'][i] for i in (0,1,2,3,7)),minimum_seconds+220)
                before=row['initial_start']+row.get('initial_run',[])+row['normal_unload']
                first_on=[next((s['t'] for s in before if fans(s,pair[1])[i]),None) for i in range(2)]
                off_edges=[]
                for i in range(2):
                    ons=[j for j,s in enumerate(before) if fans(s,pair[1])[i]]
                    off_edges.append(next((s['t'] for s in before[ons[-1]+1:] if not fans(s,pair[1])[i]),None) if ons else None)
                row.update(first_on=first_on,off_edges=off_edges)
                b.temperature(0,220);b.config({127:1})
                wait(row,'normal_reload',pair[1],lambda s:s['output'][:2]==[1,1],minimum_seconds+210)
                end=time.monotonic()+36
                while time.monotonic()<end:row.setdefault('restart_hold',[]).append(inp.sample())
                restarts=row['normal_reload']+row.get('restart_hold',[])
                on_edges=[next((s['t'] for s in restarts if fans(s,pair[1])[i]),None) for i in range(2)]
                gaps=[dict(fan=i,off_seconds=on_edges[i]-off_edges[i]) for i in range(2)
                      if off_edges[i] is not None and on_edges[i] is not None]
                runs=[dict(fan=i,on_seconds=off_edges[i]-first_on[i]) for i in range(2)
                      if first_on[i] is not None and off_edges[i] is not None]
                for run_row in runs:
                    i=run_row['fan']
                    first_on_index=next(j for j,s in enumerate(before) if fans(s,pair[1])[i])
                    last_on_index=max(j for j,s in enumerate(before) if fans(s,pair[1])[i])
                    off_index=next(j for j in range(last_on_index+1,len(before)) if not fans(before[j],pair[1])[i])
                    start_bracket=(before[first_on_index-1]['t'],before[first_on_index]['t']) if first_on_index>0 else None
                    stop_bracket=(before[last_on_index]['t'],before[off_index]['t'])
                    run_row.update(setting_seconds=minimum_seconds,
                        shortfall_seconds=max(0,minimum_seconds-run_row['on_seconds']),
                        signed_difference_seconds=run_row['on_seconds']-minimum_seconds,
                        start_edge_bracket=start_bracket,stop_edge_bracket=stop_bracket,
                        duration_bounds_seconds=([stop_bracket[0]-start_bracket[1],stop_bracket[1]-start_bracket[0]] if start_bracket else None))
                allsamples=before+restarts
                conflicts=[s for s in allsamples if (pair[1]==0 and s['output'][2] and s['output'][7])
                           or (pair[1]==3 and s['output'][3] and s['output'][7])]
                row.update(restart_gaps=gaps,run_lengths=runs,conflicting_samples=conflicts)
                for offset,label,ok in (
                    (1,'normal_chain_minimum_stop'+str(minimum_seconds),bool(gaps) and all(v['off_seconds']>=minimum_seconds-.5 for v in gaps)),
                    (2,'normal_chain_minimum_run'+str(minimum_seconds),bool(runs) and all(v['on_seconds']>=minimum_seconds-.5 for v in runs)),
                    (3,'normal_chain_speed_interlock',not conflicts)):
                    e['cases'].append(dict(id=f'O-FANTIME-{index*4+offset:03d}',label=label,
                        pair=pair,passed=ok,final=last,finished=now(),
                        limit='Observed software edges only; normal330 unload latency may extend running; repeated active stage reversals and physical terminals remain separate'))
                row['finished']=now();b.save()
            except Exception:
                row.update(error=traceback.format_exc(),finished=now());b.save()
                # Normal stop is verified before the next configuration.
                b.wr(398,0)
                if inp is None:
                    b.stop()
                    inp=Inputs(b,e);inp.temperatures({0:69})
                wait(row,'case_recovery',pair[1],lambda s:not any(s['output'][i] for i in (0,1,2,3,7)),minimum_seconds+220)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:
                try:
                    rundown=dict(pair=e['pairs'][-1]['pair'] if e['pairs'] else PAIRS[0])
                    e['final_fan_rundown']=rundown
                    wait(rundown,'fans_normally_off',rundown['pair'][1],
                         lambda s:not any(s['output'][i] for i in (0,1,2,3,7)),minimum_seconds+220)
                finally:inp.close()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--minimum-seconds',type=int,choices=range(10,301),default=30)
    p.add_argument('--fixed-variable-only',action='store_true')
    p.add_argument('--measure-minrun',action='store_true',help='Observe both fan starts then request ordinary unload immediately')
    p.add_argument('--independent-spotcheck',action='store_true',help='Explicit single-configuration scope; preserves main queue pause, uses fan_minrun_spotcheck_pause.request')
    args=p.parse_args()
    if args.independent_spotcheck and not (args.fixed_variable_only and args.measure_minrun):
        p.error('--independent-spotcheck requires --fixed-variable-only --measure-minrun')
    run(args.minimum_seconds,pairs=((2,4),) if args.fixed_variable_only else None,
        initial_hold_seconds=0 if args.measure_minrun else 11,require_both=args.measure_minrun,
        independent_spotcheck=args.independent_spotcheck)
