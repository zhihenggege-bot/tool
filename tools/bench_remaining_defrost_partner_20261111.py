"""Normal330 environment control establishes one running compressor before defrost."""
from bench_remaining_outdoor_20261111 import *
from remaining529_manual_defrost_input_20261105 import manual_defrost


def run():
    b=current_bench_class()('remaining_defrost_stopped_partner')
    e=b.log['remaining_functional']=dict(kind='defrost_stopped_healthy_partner',cases=[],
        scope='Ordinary330 full-fresh environment controller targets one compressor; legalNTC calibration, legacy HMI defrost request; no demand/timer/output/Owner writes; actual30s partner interval, BENCH general sequencing and recovery')
    row=dict(id='O-DEFROST-007',label='one_running_healthy_partner_waits_actual30seconds',samples=[])
    e['cases'].append(row)

    def sample():
        s=dict(at=now(),t=time.monotonic(),target=b.rd(881)[0],boards=[])
        for t,sy in ((b.ot,b.outsy),(b.extra[0][1].target,b.extra[0][2])):
            p=sy['Parameter'][0]
            q=dict(output=list(t.read_memory_block8(*sy['output'])),
                   alarms=[t.read16(p+2*a) for a in range(600,628)],
                   phase=[t.read16(p+2*a) for a in (1420,1421)])
            for name in ('PSC316DefrostState','PSC316DefrostStateTime','PSC316DefrostStarted',
                         'PSC316DefrostEligible','PSC316DefrostRunTime'):
                a,n=sy[name];raw=bytes(t.read_memory_block8(a,n))
                q[name]=list(struct.unpack('<'+'I'*(n//4),raw)) if name in ('PSC316DefrostStateTime','PSC316DefrostRunTime') else list(raw)
            s['boards'].append(q)
        s['owner']=b.extra[1][1].target.read8(b.sy['PSC316DefrostOwner'][0])
        row['samples'].append(s);return s

    def wait(label,predicate,seconds):
        end=time.monotonic()+seconds;heartbeat=0
        while time.monotonic()<end:
            paused();s=sample()
            assert not any(any(q['alarms']) for q in s['boards']),('healthy partner precondition',s)
            if predicate(s):row[label]=s;b.save();return s
            if time.monotonic()-heartbeat>25:
                heartbeat=time.monotonic();b.save();print('DEFROST PARTNER',label,s['target'],[q['output'][:2] for q in s['boards']],flush=True)
            time.sleep(.1)
        raise TimeoutError(label)

    try:
        b.setup(1);b.config({**HEAT,127:0,315:1,327:1,38:0,318:0,319:150})
        # With installedCN=4,14C yields ceil(4*(15-14)/15)=1.
        # Respect the existing legal calibration bound; lack of reach is an
        # unmet input precondition, never a demand-RAM substitute.
        b.temperature(2,140);b.gateway(1856,2);b.gateway(1857,2)
        b.reset_faults();b.attach_extra();b.start()
        before=wait('exactly_one_actual_compressor',lambda s:s['target']==1 and sum(sum(q['output'][:2]) for q in s['boards'])==1,240)
        unit=next(i for i,q in enumerate(before['boards']) if any(q['output'][:2]))
        running=before['boards'][unit]['output'][:2].index(1);partner=1-running
        row.update(unit=unit+1,running_compressor=running+1,stopped_healthy_partner=partner+1)
        b.wr(540,unit+1);manual_defrost(b,True,session=b.extra[1][1])
        active=wait('actual_defrost_one_still_running',lambda s:s['boards'][unit]['PSC316DefrostState']==[1]
                    and s['boards'][unit]['output'][running]==1,60)
        row['initial_partner_already_on']=bool(active['boards'][unit]['output'][partner])
        started=wait('healthy_partner_actual_start',lambda s:s['boards'][unit]['output'][partner]==1,50)
        counter=started['boards'][unit]['PSC316DefrostStateTime'][0]
        active_samples=[s for s in row['samples'] if s['boards'][unit]['PSC316DefrostState']==[1]]
        row.update(final=started,partner_start_state_seconds=counter,
            observed_from_first_active_s=started['t']-active['t'],
            passed=not row['initial_partner_already_on'] and 30<=counter<=34 and
                   all(s['boards'][unit]['output'][running]==1 for s in active_samples) and
                   not any(s['boards'][unit]['output'][partner] and s['boards'][unit]['PSC316DefrostStateTime'][0]<30 for s in active_samples),
            finished=now(),limit='Actual state counter and software outputs, no timer writes; legacy command input route limitation and physical contactor timing remain separate')
    except BaseException:e['error']=traceback.format_exc();row.setdefault('passed',False);b.save();raise
    finally:
        try:b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
