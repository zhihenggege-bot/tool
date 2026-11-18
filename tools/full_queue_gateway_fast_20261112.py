"""Adjacent ordinary writes, avoiding a slow multi-read between busy requests."""
from full_queue_context_20261112 import *

def run():
    b=current_bench_class()('gateway_adjacent_requests_recheck');b.attach_extra()
    e=b.log['gateway_recheck']=dict(cases=[],scope='Stopped boards; adjacent normal HMI requests, no forced bus/job state')
    original={a:b.rd(a)[0] for a in (1832,1880)}
    targets={1832:(b.ot,b.outsy),1880:(b.extra[0][1].target,b.extra[0][2])}
    def actual(a):
        t,sy=targets[a];return t.read16(sy['Parameter'][0]+2*167)
    def idle():
        end=time.monotonic()+70
        while b.extra[1][1].target.read8(b.sy['PSC316WriteJob'][0]):
            assert time.monotonic()<end,'gateway idle timeout';time.sleep(.1)
    def write(a,v):
        idle()
        if actual(a)==b.rd(a)[0]==v:return
        b.c.write_single_register(1,a,v);idle()
        end=time.monotonic()+30
        while actual(a)!=v or b.rd(a)[0]!=v:
            assert time.monotonic()<end,'gateway destination/mirror settle timeout';time.sleep(.1)
    try:
        assert b.rd(398)==[0] and b.rd(709)==[0]
        for attempt in range(3):
            for a in original:write(a,0)
            row=dict(attempt=attempt,started=now());e['cases'].append(row)
            b.c.write_single_register(1,1832,1)
            row['first_response_t']=time.monotonic()
            row['active_before_second']=b.extra[1][1].target.read8(b.sy['PSC316WriteJob'][0])
            b.c.write_single_register(1,1880,1)
            row['second_response_t']=time.monotonic()
            row['diagnostic_after_second']=b.rd(1920,6)
            idle()
            row['final_destinations']={str(a):actual(a) for a in original}
            row['final_mirrors']={str(a):b.rd(a)[0] for a in original}
            row['busy_rejection_proven']=row['diagnostic_after_second'][1:3]==[3,3] and actual(1832)==1 and actual(1880)==0
            row['verdict']='busy_rejection_and_first_destination_verified' if row['busy_rejection_proven'] else 'collision_not_proven_review_actual_trace'
            b.save();print('GATEWAY ADJACENT',attempt,row['verdict'],flush=True)
    finally:
        try:
            b.wr(398,0)
            for a,v in original.items():write(a,v)
        finally:b.finish();e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)
    dump(DAY/'gateway_fast_recheck_executed.json',dict(at=now(),evidence=str(b.path),restored=b.log.get('restored'),cases=e['cases']))

if __name__=='__main__':run()
