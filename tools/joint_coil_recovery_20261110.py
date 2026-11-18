"""Supplement exact 5C/120s recovery; legal 1-minute trip setup, no timers forced."""
from joint_priority_20261110 import *
from nonvent_coil_process_input_20261109 import ProcessNtcInput


def run():
    b=TodayBench('four_coil_120s_recovery_corrected_clock');fixture=None
    e=dict(started=now(),status='running',samples=[],release_times={},scope='4 installed circuits; legal 1-minute low hold only establishes protection; exact5C and real120s recovery; complements separate300s trip evidence')
    b.log['priority_case']=e;b.save()
    def sample(label):
        s=b.snapshot(label);s.update(t=time.monotonic(),flags=b.rd(640,8),temps=[signed16(b.rd(a)[0]) for a in (515,516,514,517)])
        e['samples'].append(s);return s
    try:
        b.setup(0);b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,416:100,417:1,418:0,315:0,320:0,346:0,
            245:1,247:0,329:2,330:0,331:0,365:1,411:200,10:500,12:500,
            110:1,111:-20,112:50,114:2,491:0,490:0,489:0,488:0})
        fixture=ProcessNtcInput(b)
        for ch in range(4,8):fixture.set(ch,100)
        b.temperature(0,290);b.reset_faults();b.start()
        b.wait('recovery setup actual four cooling',lambda s:all(v==2 for p in s['outdoor_status'] for v in p),180)
        for ch in range(4,8):fixture.set(ch,-21)
        began=time.monotonic();heartbeat=began
        while True:
            s=sample('legal60s setup trip');assert not any(s['faults']) and not any(s['flags'][4:]),s
            if all(s['flags'][:4]):break
            assert time.monotonic()-began<75,s
            if time.monotonic()-heartbeat>25:print('RECOVERY SETUP',round(time.monotonic()-began,1),s['flags'],flush=True);heartbeat=time.monotonic();b.save()
            time.sleep(.35)
        started={}
        for i in range(4):
            fixture.set(i+4,50);started[i]=fixture.log['events'][-1]['t']
        e['release_input_times']=started;b.save();began=time.monotonic();heartbeat=began
        while len(e['release_times'])<4:
            s=sample('exact5C recovery corrected clock');assert not any(s['faults']) and s['temps']==[50]*4,s
            for i in range(4):
                if not s['flags'][i] and str(i) not in e['release_times']:
                    dt=s['t']-started[i];e['release_times'][str(i)]=dict(elapsed_from_input_request_s=dt,sample=s)
                    assert 118.9<=dt<=123,('recovery outside1s tick and observation allowance',i,dt)
            assert time.monotonic()-began<130,s
            if time.monotonic()-heartbeat>25:print('RECOVERY120',round(time.monotonic()-began,1),s['flags'],flush=True);heartbeat=time.monotonic();b.save()
            time.sleep(.3)
        e['running_again']=b.wait('recovery restores actual four cooling',lambda s:all(v==2 for p in s['outdoor_status'] for v in p),200)
        e['status']='软件子范围通过：四路5℃连续120计时及自动解禁，实际四压机制冷反馈恢复';b.save()
        print('RECOVERY COMPLETE',{k:v['elapsed_from_input_request_s'] for k,v in e['release_times'].items()},flush=True)
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:
            if fixture:
                for ch in range(4,8):fixture.set(ch,100)
                time.sleep(1);fixture.close();time.sleep(2)
            if any(b.rd(640,8)):b.wait('natural healthy recovery cleanup',lambda s:not any(b.rd(640,8)),135,True)
            b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
