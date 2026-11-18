"""All four installed circuits: independent raw inputs, read-only counters."""
from joint_v1059_context_20261112 import *
from nonvent_coil_process_input_20261109 import ProcessNtcInput

def run():
    b=current_bench_class()('four_coil_continuity_mode');fixture=None
    e=b.log['remaining_functional']=dict(kind='four_installed_coils_continuity',cases=[],
        scope='Installed circuits1..4 together; raw ADC/filter inputs; legal1min holds; actual counters and software flags; complements separate300/120s scope')
    row=dict(id='T15-009',label='all_four_low_release_continuity_and_mode_abort',samples=[],events={})
    e['cases'].append(row)
    def temperatures(value):
        for ch in range(4,8):fixture.set(ch,value)
        return time.monotonic()
    def until(label,predicate,seconds,after=0):
        end=time.monotonic()+seconds;heartbeat=0
        while time.monotonic()<end:
            if fixture.error:raise RuntimeError(fixture.error)
            rows=fixture.log['read_only_counters'];counter=rows[-1] if rows else None
            s=b.snapshot(label);s.update(counter=counter,flags=b.rd(640,8),
                temperatures10=[signed16(v) for v in b.rd(514,4)])
            row['samples'].append(s)
            assert not any(s['faults']) and not any(s['flags'][4:]),s
            if counter and counter['t']>=after and time.monotonic()-counter['t']<3 and predicate(s):
                row['events'][label]=s;b.save();print('FOUR COIL CONTINUITY',label,flush=True);return s
            if time.monotonic()-heartbeat>=25:heartbeat=time.monotonic();b.save()
            time.sleep(.25)
        raise TimeoutError(label)
    try:
        b.setup(0);b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,416:100,417:1,418:0,315:0,320:0,346:0,
            245:1,247:0,329:2,330:0,331:0,365:1,411:200,10:500,12:500,
            110:1,111:-20,112:50,114:1,491:0,490:0,489:0,488:0})
        fixture=ProcessNtcInput(b);temperatures(100)
        b.temperature(0,290);b.reset_faults();b.start()
        b.wait('four installed circuits actual cooling',lambda s:all(v==2 for pair in s['outdoor_status'] for v in pair),210)
        at=temperatures(-21)
        until('low15_before_break',lambda s:all(v>=15 for v in s['counter']['low'][:4]) and not any(s['flags']),30,at)
        at=temperatures(-20)
        until('equal_minus2_resets_all_four_low_counts',lambda s:s['counter']['converted_temp10']==[-20]*4 and not any(s['counter']['low'][:4]) and not any(s['flags']),10,at)
        at=temperatures(-21)
        until('fresh60s_trips_all_four',lambda s:s['flags'][:4]==[1]*4,75,at)
        at=temperatures(50)
        until('release15_before_break',lambda s:all(v>=15 for v in s['counter']['release'][:4]) and s['flags'][:4]==[1]*4,30,at)
        at=temperatures(49)
        until('4point9_resets_all_four_release_counts',lambda s:s['counter']['converted_temp10']==[49]*4 and not any(s['counter']['release'][:4]) and s['flags'][:4]==[1]*4,10,at)
        at=temperatures(50)
        until('fresh60s_clears_all_four',lambda s:not any(s['flags']),75,at)
        at=temperatures(-21)
        until('low15_before_mode_change',lambda s:all(v>=15 for v in s['counter']['low'][:4]) and not any(s['flags']),30,at)
        at=time.monotonic();b.c.write_single_register(1,236,1)
        final=until('mode_stop_resets_all_four_low_counts',lambda s:s['state'][9] in (3,4) and not any(s['counter']['low'][:4]) and not any(s['flags']) and s['counter']['converted_temp10']==[-21]*4,12,at)
        row.update(passed=True,final=final,finished=now())
    except BaseException:row.update(passed=False,error=traceback.format_exc());b.save();raise
    finally:
        try:
            if fixture:
                temperatures(100);time.sleep(1);fixture.close()
            if any(b.rd(640,8)):b.wait('natural healthy coil cleanup',lambda s:not any(b.rd(640,8)),80,True)
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

if __name__=='__main__':run()
