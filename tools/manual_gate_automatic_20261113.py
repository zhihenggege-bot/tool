"""Live manual fan gate checks followed by ordinary automatic sequencing."""
import manual_reset_fix_context_20261113 as ctx
from gap_cases_20261113 import wait
from bench_remaining_outdoor_20261111 import HEAT

g=ctx.g

def run():
    b=g.Bench('fan_interlock_and_automatic_regression')
    e=b.log['manual_automatic_regression']=dict(started=g.now(),checks=[],samples=[])
    def read():return g.sample(b,'manual_automatic_regression')
    def capture(label,predicate,seconds=40,hold=2):
        row=dict(check=label,started=g.now());e['checks'].append(row)
        s=wait(b,row,label,read,predicate,seconds,hold)
        row['passed']=True;b.save();return s
    def comp(s,want):return all(q['output'][:2]==want for q in s['boards'])
    def manual_outputs(fan):
        settings={**{a:0 for a in range(1302,1318)},1301:1}
        for start in (1302,1310):settings.update({start:1,start+1:1,start+2:fan})
        b.config(settings)
    try:
        b.setup(1);b.config(HEAT);b.temperature(0,220);b.reset_faults();b.attach_extra()
        b.config({1300:1});manual_outputs(0)
        capture('manual_compressor_request_without_fan_blocked',lambda s:comp(s,[0,0]) and all(q['alarms']==[0]*28 for q in s['boards']))
        manual_outputs(1)
        capture('manual_fan_on_allows_compressors',lambda s:comp(s,[1,1]) and all(q['output'][2]==1 for q in s['boards']))
        manual_outputs(0)
        capture('manual_fan_off_cuts_compressors',lambda s:comp(s,[0,0]) and all(q['output'][2]==0 for q in s['boards']))
        b.config({**{a:0 for a in range(1302,1318)},1301:0,1300:0})
        capture('manual_released_outputs_off',lambda s:all(not any(q['output'][i] for i in (0,1,2,3,4,5,7)) for q in s['boards']))
        e['automatic_start_requested_at']=g.now();b.wr(398,1)
        start=dict(samples=[])
        wait(b,start,'automatic_all_four_compressors_running',read,lambda s:comp(s,[1,1]) and s['state'][9]==2,280,3)
        e['automatic_start_samples']=start['samples'];edges=[]
        for unit in range(2):
            rows=start['samples']
            first_fan=next(s for s in rows if any(s['boards'][unit]['output'][i] for i in (2,3,7)))
            first_comp=next(s for s in rows if any(s['boards'][unit]['output'][:2]))
            edge=dict(unit=unit+1,fan_observed_at=first_fan['at'],compressor_observed_at=first_comp['at'],
                      observed_fan_lead_s=first_comp['t']-first_fan['t'])
            assert edge['observed_fan_lead_s']>1,edge
            assert all(any(s['boards'][unit]['output'][i] for i in (2,3,7)) for s in rows if any(s['boards'][unit]['output'][:2]))
            edges.append(edge)
        e['automatic_fan_lead']=edges
        e['automatic_stop_requested_at']=g.now();b.wr(398,0)
        stopped=dict(samples=[])
        wait(b,stopped,'automatic_normal_stop_completed',read,
             lambda s:s['state'][9]==0 and all(not any(q['output'][i] for i in (0,1,2,3,4,5,7)) for q in s['boards']),280,2)
        e['automatic_stop_samples']=stopped['samples'];e['passed']=True
        b.save();print('MANUAL FAN GATES AND AUTOMATIC SEQUENCE PASS',edges,flush=True)
    except BaseException:
        e['error']=g.traceback.format_exc();b.save();raise
    finally:
        try:
            if b.rd(709)==[0]:b.config({**{a:0 for a in range(1302,1318)},1301:0,1300:0})
            b.finish()
        finally:e['finished']=g.now();b.save()
