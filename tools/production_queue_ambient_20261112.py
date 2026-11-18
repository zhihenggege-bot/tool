"""Observe unchanged PRODUCTION ambient hold through acquisition inputs only."""
from production_queue_context_20261112 import *
from bench_remaining_outdoor_20261111 import Inputs,HEAT
from continuous_special_stages_v1055_20261109 import paused

def run():
    b=current_bench_class()('formal_ambient_recovery300');inp=None
    e=b.log['formal_timing']=dict(ids=['T14-024'],points=[],scope=
        'PRODUCTION real300s ambient hold; raw NTC0 acquisition input; normal demand. Keep user-deferred ambient policy unchanged; software readback only')
    try:
        b.setup(1);b.config(HEAT);b.temperature(0,220);b.reset_faults()
        inp=Inputs(b,e);inp.temperatures({0:80});b.start()
        end=time.monotonic()+900
        while True:
            s=inp.sample()
            if s['output'][:2]==[1,1]:break
            assert time.monotonic()<end,'formal ambient initial load timeout'
        for label,temp,seconds in (('running_above_RWSplus2_hold',201,310),
            ('lower_than_RWS_restore_hold',179,310)):
            issued=time.monotonic();inp.temperatures({0:temp})
            row=dict(label=label,temp10=temp,samples=[],requested_t=issued);e['points'].append(row)
            exact=None;heartbeat=0;end=time.monotonic()+seconds+35
            while True:
                paused();s=inp.sample();s['actual_temp10']=signed16(s['params']['1422'])
                row['samples'].append(s)
                if s['actual_temp10']==temp:
                    if exact is None:exact=s['t']
                    if s['t']-exact>=seconds:break
                elif exact is not None:row.setdefault('input_interruptions',[]).append(s);exact=None
                assert time.monotonic()<end,'formal ambient stable input timeout'
                if time.monotonic()-heartbeat>30:b.save();heartbeat=time.monotonic();print('FORMAL AMBIENT',label,round(s['t']-issued,1),flush=True)
            row.update(first_exact_t=exact,final=s,finished=now());b.save()
        e.update(executed=True,full_acceptance=False,remaining='Current heating upper ambient policy traced; cooling high-side60s and lower300s branches remain separate scopes')
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
        finally:
            b.finish();b.save();print('EVIDENCE',b.path,flush=True)
