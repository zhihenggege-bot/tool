"""Four installed evaporator loops: real 300s trip /120s recovery, ADC input only."""
from nonvent_ntc_input_boundaries_20261109 import *
import subprocess,sys


def run():
    b=CheckedBench('four_coil_real_300_120');fixture=None
    e=dict(passed=False,samples=[],trip_times={},release_times={},
        scope='Four installed loops, real 300/120s under BENCH firmware; ADC/filter input simulation, no electrical source/terminal test')
    for c in range(4):b.log['cases'][f'T15-{c+1:03d}']=e
    b.save()
    try:
        b.setup(0);b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,416:100,417:1,418:0,
            315:0,320:0,346:0,245:1,247:0,329:2,330:0,331:0,
            365:1,411:200,10:500,12:500,110:5,111:-20,112:50,114:2,
            491:0,490:0,489:0,488:0})
        fixture=RawNtcInput(b)
        for ch in range(4,8):fixture.set(ch,100)
        b.temperature(0,290);b.reset_faults();b.start()
        b.wait('four coil protection precondition real cooling',lambda s:all(v==2 for p in s['outdoor_status'] for v in p),180)
        temps=(515,516,514,517);started={};began=time.monotonic();heartbeat=began;next_index=0
        while len(e['trip_times'])<4:
            paused();elapsed=time.monotonic()-began
            if next_index<4 and elapsed>=next_index*6:
                input_requested=time.monotonic()
                fixture.set(4+next_index,-21)
                b.wait('coil input -2.1C '+str(next_index+1),lambda s:signed16(b.rd(temps[next_index])[0])==-21,10)
                started[next_index]=input_requested;next_index+=1
            s=b.snapshot('coil low continuous real clock');s.update(t=time.monotonic(),flags=b.rd(640,8),temps=[signed16(b.rd(a)[0]) for a in temps],actual_count=b.rd(119)[0]);e['samples'].append(s)
            assert not any(s['faults']),s
            assert s['flags'][4:]==[0]*4,('uninstalled loops falsely tripped',s)
            for i in range(4):
                if i not in started:assert s['flags'][i]==0,s
                elif s['flags'][i]:
                    if str(i) not in e['trip_times']:
                        dt=s['t']-started[i];e['trip_times'][str(i)]=dict(elapsed_s=dt,sample=s)
                        assert 298.5<=dt<=302,('low timer not 300s',i,dt)
                elif s['t']-started[i]>303:raise AssertionError(('coil did not trip',i,s))
            if time.monotonic()-heartbeat>=25:
                print('COIL REAL LOW',round(elapsed,1),s['flags'],s['actual_count'],flush=True);heartbeat=time.monotonic();b.save()
            assert elapsed<340;time.sleep(.25)
        e['low_input_start_times']=started
        # Each loop now blocked independently. Keep the same four healthy
        # ADC inputs at the inclusive release threshold without resetting flags.
        release_started={}
        for i in range(4):
            input_requested=time.monotonic()
            fixture.set(i+4,50);b.wait('coil release threshold5C '+str(i+1),lambda s:signed16(b.rd(temps[i])[0])==50,10);release_started[i]=input_requested
        began=time.monotonic();heartbeat=began
        while len(e['release_times'])<4:
            paused();s=b.snapshot('coil release continuous real clock');s.update(t=time.monotonic(),flags=b.rd(640,8),temps=[signed16(b.rd(a)[0]) for a in temps]);e['samples'].append(s)
            assert not any(s['faults']),s
            for i in range(4):
                if not s['flags'][i] and str(i) not in e['release_times']:
                    dt=s['t']-release_started[i];e['release_times'][str(i)]=dict(elapsed_s=dt,sample=s)
                    assert 118.5<=dt<=123,('release timer not120s',i,dt)
            if time.monotonic()-heartbeat>=25:
                print('COIL REAL RELEASE',round(time.monotonic()-began,1),s['flags'],flush=True);heartbeat=time.monotonic();b.save()
            assert time.monotonic()-began<130;time.sleep(.25)
        e['running_again']=b.wait('coil recovery allows four actual cooling feedback again',lambda s:all(v==2 for p in s['outdoor_status'] for v in p),200)
        e['passed']=True;b.save()
        for i in range(4):
            b.record_local(f'T15-{i+1:03d}',True,f'V10.55已安装回路{i+1}：原始NTC ADC/滤波INPUT模拟-2.1℃，按6s错开四路，低温标志实际在{e["trip_times"][str(i)]["elapsed_s"]:.3f}s置位；其它未到时回路未提前置位，未安装四路保持0。恢复精确5℃后{e["release_times"][str(i)]["elapsed_s"]:.3f}s自动解禁，随后四台真实制冷反馈恢复。未写保护计时/故障标志/输出；正式秒数在BENCH板上真实计时，非物理信号源及端子；中断连续性另验。',e)
        data=json.loads(RESULTS.read_text('utf8'))
        for i in range(4):data[f'T15-{i+1:03d}']['inputs']='NTC4..7 raw ADC/filter INPUT simulation, actual300s/120s; no timer/flag/output forcing'
        dump(RESULTS,data)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:
        try:
            if fixture:
                for ch in range(4,8):fixture.set(ch,100)
                time.sleep(1);fixture.close();time.sleep(2)
            if any(b.rd(640,8)):
                # Protection flags are controller state, never manually clear
                # them: let healthy real inputs finish their normal release.
                b.wait('cleanup healthy coils release naturally',lambda s:not any(b.rd(640,8)),135,True)
            b.stop()
        finally:b.finish()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    path=D/('coil_real_time_controller_'+time.strftime('%H%M%S')+'.json');q=dict(started=now(),status='waiting_without_hardware',dependency=str(a.after),ventilation='Deferred by user');dump(path,q)
    try:
        while True:
            paused();d=json.loads(a.after.read_text('utf8'))
            if d.get('finished'):break
            time.sleep(3)
        assert d.get('status')=='completed',d
        from nonvent_supplement_v1055_20261109 import restored_latest
        restored_latest();q['status']='running';dump(path,q)
        # Rerun zero-demand boundaries with the corrected independent starts.
        winter();restored_latest();run();restored_latest();q['checks']=[]
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8');q['checks'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(path,q);assert proc.returncode==0
        q['status']='completed'
    except BaseException:q.update(status='stopped_on_error',error=traceback.format_exc());raise
    finally:q['finished']=now();dump(path,q)
