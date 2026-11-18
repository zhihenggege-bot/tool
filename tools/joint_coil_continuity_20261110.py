"""Installed circuit1: interrupt low/recovery thresholds and request mode change."""
from joint_priority_20261110 import *
from nonvent_coil_process_input_20261109 import ProcessNtcInput


def run(mode_only=False):
    b=TodayBench('T15-009_coil_mode_async' if mode_only else 'T15-009_coil_continuity');fixture=None
    e=dict(started=now(),status='running',samples=[],events={},scope='Circuit1 only; legal1min low/release settings, independent raw input, counters read-only. Complements separate300/120s tests; not8-circuit or physical-source acceptance')
    b.log['priority_case']=e;b.save()
    def until(label,predicate,timeout):
        began=time.monotonic();heartbeat=began
        while True:
            rows=fixture.log['read_only_counters'];d=rows[-1] if rows else None
            s=b.snapshot(label);s.update(counter=d,flags=b.rd(640,8),temp=signed16(b.rd(515)[0]),requested_mode=b.rd(236)[0]);e['samples'].append(s)
            assert not any(s['faults']) and not any(s['flags'][1:]),s
            if d and predicate(s):e['events'][label]=s;b.save();print('CONTINUITY',label,'PASS',flush=True);return s
            assert time.monotonic()-began<timeout,(label,s)
            if time.monotonic()-heartbeat>25:print('CONTINUITY WAIT',label,round(time.monotonic()-began,1),flush=True);heartbeat=time.monotonic();b.save()
            time.sleep(.25)
    try:
        b.setup(0);b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,416:100,417:1,418:0,315:0,320:0,346:0,
            245:1,247:0,329:2,330:0,331:0,365:1,411:200,10:500,12:500,
            110:1,111:-20,112:50,114:1,491:0,490:0,489:0,488:0})
        fixture=ProcessNtcInput(b)
        for ch in range(4,8):fixture.set(ch,100)
        b.temperature(0,290);b.reset_faults();b.start()
        b.wait('circuit1 actual cooling continuity setup',lambda s:s['outdoor_status'][0][0]==2,150)
        fixture.set(4,-21)
        if mode_only:
            until('low15_before_mode_change',lambda s:s['counter']['low'][0]>=15 and s['flags'][0]==0,25)
            e['mode_request']=dict(at=now(),requested=1,protocol='normal Modbus236; mode retains active value while pending stop')
            b.c.write_single_register(1,236,1)
            until('mode_change_stopping_clears_low_count',lambda s:s['state'][9] in (3,4) and s['counter']['low'][0]==0 and s['flags'][0]==0 and s['temp']==-21,8)
            b.wr(398,0)
            e['status']='回路1模式切换子范围通过：异步模式请求触发正常停止，低温输入仍在时计数清零';b.save();return
        until('low15_before_break',lambda s:s['counter']['low'][0]>=15 and s['flags'][0]==0,25)
        fixture.set(4,-20)
        until('equal_minus2_breaks_low_count',lambda s:s['temp']==-20 and s['counter']['low'][0]==0 and s['flags'][0]==0,6)
        fixture.set(4,-21)
        until('restarted_low_reaches60_and_trips',lambda s:s['flags'][0]==1,70)
        fixture.set(4,50)
        until('release15_before_break',lambda s:s['counter']['release'][0]>=15 and s['flags'][0]==1,25)
        fixture.set(4,49)
        until('4point9_breaks_release_count_keeps_fault',lambda s:s['temp']==49 and s['counter']['release'][0]==0 and s['flags'][0]==1,6)
        fixture.set(4,50)
        until('restarted_release_reaches60_and_clears',lambda s:s['flags'][0]==0,70)
        fixture.set(4,-21)
        until('low15_before_mode_change',lambda s:s['counter']['low'][0]>=15 and s['flags'][0]==0,25)
        b.c.write_single_register(1,236,1)
        until('mode_change_stopping_clears_low_count',lambda s:s['state'][9] in (3,4) and s['counter']['low'][0]==0 and s['flags'][0]==0 and s['temp']==-21,8)
        b.wr(398,0)
        e['status']='回路1软件子范围通过：低温等号打断、恢复4.9℃打断、重新累计及模式切换停机清计时；1分钟合法设定';b.save()
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:
            if fixture:
                for ch in range(4,8):fixture.set(ch,100)
                time.sleep(1);fixture.close();time.sleep(2)
            if any(b.rd(640,8)):b.wait('natural healthy continuity cleanup',lambda s:not any(b.rd(640,8)),70,True)
            b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode-only',action='store_true');a=p.parse_args();run(a.mode_only)
