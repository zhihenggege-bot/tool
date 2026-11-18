"""Stable LP input via normal330 polarity settings, with read-only probes.

The global setting affects both outdoor units. Check the other compressor in
each unit stays healthy; do not claim the peer unit has an inactive LP input.
No fixture races the ordinary master broadcasts and no DI/fault bit is forced.
"""
from joint_v1242_context_20261112 import *
from bench_remaining_outdoor_20261111 import HEAT
import struct
import continuous_special_stages_v1055_20261109 as pause_module
pause_module.PAUSE=R/'.codex-tmp/four_followups_pause.request'


def run():
    pause_module.paused()
    b=current_bench_class()('LP_stable_normal_polarity')
    e=b.log['stable_low_pressure']=dict(cases=[],
        scope='Normal330 global outdoor input-polarity configuration; both units may trip the tested compressor; other compressor in each unit must continue; probes read only')
    b.attach_extra()
    targets=[(b.ot,b.outsy),(b.extra[0][1].target,b.extra[0][2])]

    def sample(ch,alarm):
        pause_module.paused()
        rows=[]
        for t,sy in targets:
            p=sy['Parameter'][0]
            rows.append(dict(raw=t.read8(sy[f'X_{ch:02d}'][0]),
                debounced=t.read8(sy[f'X{ch:02d}_En'][0]),
                debounce_ticks=t.read16(sy[f'X{ch:02d}_Cnt'][0]),
                polarity=t.read16(p+2*(ch+2)),
                alarm=t.read16(p+2*alarm),
                layer=t.read16(p+2*1501),
                output=list(t.read_memory_block8(*sy['output'])),
                run_seconds=list(struct.unpack('<5I',bytes(t.read_memory_block8(*sy['CompRunTime'])))),
                low_enabled=list(struct.unpack('<5I',bytes(t.read_memory_block8(*sy['EnableCheckLow']))))))
        mirrors=[b.rd(2022+(u*128)+alarm-600)[0] for u in range(2)]
        return dict(at=now(),t=time.monotonic(),boards=rows,mirrors=mirrors,page=b.rd(540)[0])

    def observe(row,label,ch,alarm,predicate,seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            s=sample(ch,alarm);row.setdefault(label,[]).append(s)
            if predicate(s):b.save();return s
            time.sleep(.15)
        b.save();raise TimeoutError(label)

    try:
        b.setup(1);b.config(HEAT);b.temperature(0,220);b.reset_faults();b.start()
        b.wait('stable LP: all four healthy',lambda s:all(v==3 for pair in s['outdoor_status'] for v in pair),360)
        for ch,alarm,comp in ((1,600,0),(3,601,1)):
            row=dict(ch=ch,alarm=alarm,comp=comp,started=now());e['cases'].append(row)
            address=ch+2;old=b.rd(address)[0];row['original_global_polarity']=old
            assert old in (0,1)
            changed=False
            try:
                delay=b.rd(27)[0]
                observe(row,'eligible',ch,alarm,lambda s:all(
                    x['output'][:2]==[1,1] and not x['alarm'] and not x['raw']
                    and x['run_seconds'][comp]>delay and x['low_enabled'][comp]
                    for x in s['boards']),max(360,delay+180))
                b.config({address:1-old});changed=True
                edge=observe(row,'assertion',ch,alarm,lambda s:all(x['raw']==x['debounced']==x['alarm']==1
                    and x['output'][comp]==0 and x['output'][1-comp]==1 for x in s['boards']),90)
                hold_end=time.monotonic()+45
                while time.monotonic()<hold_end:
                    row.setdefault('hold',[]).append(sample(ch,alarm));time.sleep(.15)
                stable=all(x['raw']==x['debounced']==x['alarm']==1 and x['output'][comp]==0
                    and x['output'][1-comp]==1 for s in row['hold'] for x in s['boards'])
                mirror_seen=all(any(s['mirrors'][u]==1 for s in row['hold']) for u in range(2))
                row.update(source_and_protection_continuous=stable,mirrors_seen=mirror_seen,
                    hold_s=row['hold'][-1]['t']-edge['t'],passed=stable and mirror_seen)
                print('STABLE LP',ch,row['passed'],'source',stable,'mirrors',mirror_seen,flush=True)
            except Exception as exc:
                row.update(passed=False,error=repr(exc))
            finally:
                if changed:b.config({address:old})
                # LP must clear by removing the source, without a reset pulse.
                observe(row,'automatic_recovery',ch,alarm,lambda s:all(not x['raw'] and not x['debounced']
                    and not x['alarm'] and not x['layer'] for x in s['boards']) and not any(s['mirrors']),90)
                row.update(recovery_without_reset=True,finished=now());b.save()
    finally:
        try:b.wr(398,0)
        finally:
            b.finish();e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    run()
