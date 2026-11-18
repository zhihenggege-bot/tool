"""Run only after the boundary retry has closed COM6 and restored parameters.

Establish demand trajectories through legal room calibration and real scans.
No demand, history, output, timer or target memory is written.
"""
from v1055_bench_context_20261109 import *
from remaining_pid_live_20261106 import Reader
from continuous_followups_v1055_20261109 import CheckedBench, paused
import subprocess, sys


def collect(b, reader, direction, seconds=90):
    phase=dict(direction=direction, ticks=[], rejected_reads=[], started=now())
    b.log.setdefault('target_phases', []).append(phase)
    before=reader.read();began=time.monotonic();heartbeat=began
    while time.monotonic()-began<seconds:
        paused();after=reader.read()
        changed=after['count']<before['count'] or any(after[k]!=before[k] for k in ('n','valid','history','residual'))
        if not changed:
            before=after;time.sleep(.025);continue
        display=b.rd(872,10);actual=b.rd(119)[0];cn=b.rd(2678)[0]
        checked=reader.read()
        fields=('n','valid','history','residual','sign')
        coherent=all(checked[k]==after[k] for k in fields) and checked['count']>=after['count']
        if not coherent:
            phase['rejected_reads'].append(dict(before=before,after=after,checked=checked,display=display))
            before=checked;continue
        estimated_scans=round((after['t']-before['t']+(before['count']-after['count'])/10)/2)
        if estimated_scans!=1:
            phase['rejected_reads'].append(dict(reason='not exactly one observed scan',before=before,after=after,estimated_scans=estimated_scans))
            before=checked;continue
        ys=signed16(display[5]);expected=reader.oracle(before,after['history'][0],10,2,0,2,20,ys)
        sign=after['sign'];n=after['n'];keep=bool(b.rd(127)[0])
        want=(cn*n+999)//1000 if sign>0 else cn*n//1000 if sign<0 else actual
        if keep and sign:want=max(1,want)
        # N=0 with positive fractional Z is a separate interpretation edge;
        # this trajectory starts above zero, so do not count it here.
        formula=all(after[k]==expected[k] for k in fields) and signed16(display[7])==expected['z']
        output=b.snapshot('PID target '+str(direction))
        row=dict(before=before,after=after,expected=expected,display=display,
                 installed=cn,target=display[9],actual_running=actual,expected_target=want,
                 reheat_enabled=keep,ys=ys,formula_matches=formula,
                 output=output,
                 passed=formula and display[8]==n and display[9]==want and cn==4 and ys==0 and not any(output['faults']) and output['state'][9]==2,
                 fractional_count=(cn*n)%1000!=0)
        phase['ticks'].append(row);b.save()
        print('PID TARGET',keep,direction,'N',n,'Z',signed16(display[7]),'target',display[9],'expected',want,'passed',row['passed'],flush=True)
        before=checked
        useful=[t for t in phase['ticks'] if t['after']['valid']==2 and t['after']['sign']==direction]
        endpoint=1000 if direction>0 else 0
        fractions={t['after']['n'] for t in useful if t['fractional_count']}
        if len(useful)>=8 and len(fractions)>=3 and any(t['after']['n']==endpoint for t in useful):break
        if time.monotonic()-heartbeat>25:b.save();heartbeat=time.monotonic()
    useful=[t for t in phase['ticks'] if t['after']['valid']==2 and t['after']['sign']==direction]
    phase.update(duration_s=time.monotonic()-began,
        fractional_demands=sorted({t['after']['n'] for t in useful if t['fractional_count']}),
        endpoint_seen=any(t['after']['n']==(1000 if direction>0 else 0) for t in useful))
    phase['passed']=bool(phase['ticks']) and all(t['passed'] for t in phase['ticks']) and len(useful)>=8 and len(phase['fractional_demands'])>=3 and phase['endpoint_seen']
    b.save();return phase


def run(reheat):
    b=CheckedBench('pid_target_trajectories_reheat_'+str(reheat));reader=None
    try:
        b.setup(0)
        b.config({315:0,327:1,128:1,127:reheat,129:0,332:reheat,333:0,
            125:0,126:0,248:0,334:0,160:250,161:250,412:2,120:20,
            416:10,417:2,418:0,347:5,348:100,349:0,
            329:2,330:0,331:0,346:0,320:0,30:0,12:500})
        # NTC2 is irrelevant to room PID; preserve its physical fixture.
        b.temperature(0,260);reader=Reader(b,'cool');b.reset_faults();b.start()
        assert b.rd(2678)[0]==4
        for direction,cid,temp in ((1,'T09-026' if reheat else 'T09-023',260),
                                   (-1,'T09-027' if reheat else 'T09-024',240)):
            b.temperature(0,temp)
            phase=collect(b,reader,direction)
            b.record_local(cid,phase['passed'],
                f'V10.55 BENCH室内制冷PID，再热启用={reheat}，真实'+('加载' if direction>0 else '卸载')+
                f'扫描{len(phase["ticks"])}拍；CN=4，逐拍核对规格PID及'+('ceil' if direction>0 else 'floor')+
                ('并至少1台' if reheat else '')+'，含至少3个非整数台数需求与需求端点；合法室温校准，不写需求/目标/输出RAM。仅软件链路，压机动力、端子及正式时序另验。',phase)
            assert phase['passed'],(cid,'retain actual mismatch or missing coverage; do not force pass')
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        if reader:reader.close()
        b.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    dependency=a.after.resolve();journal=D/('continuous_pid_target_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),dependency=dependency.relative_to(R).as_posix(),status='waiting_without_hardware',actions=[]);dump(journal,q)
    while True:
        paused()
        try:prior=json.loads(dependency.read_text('utf8'))
        except (OSError,ValueError):prior={}
        if prior.get('finished'):break
        time.sleep(5)
    # A failed test can still have restored safely, but inspect the exact retry
    # evidence before opening the port; never select an unrelated latest batch.
    candidates=list(D.glob('remaining571_heat_dynamic_special_time_range_retest_*.json'))
    latest=max(candidates,key=lambda v:v.stat().st_mtime) if candidates else None
    recovery=json.loads(latest.read_text('utf8')) if latest else {}
    if not recovery.get('restored') or recovery.get('cleanup_error'):
        q.update(status='predecessor_restore_unconfirmed_no_hardware',finished=now());dump(journal,q);return
    q.update(status='running',started_test=now());dump(journal,q)
    try:
        for reheat in (0,1):
            row=dict(reheat=reheat,started=now());q['actions'].append(row);dump(journal,q)
            try:run(reheat);row['status']='completed'
            except Exception:
                row.update(status='failed_or_unavailable',error=traceback.format_exc())
                paths=list(D.glob('remaining571_heat_dynamic_pid_target_trajectories_reheat_'+str(reheat)+'_*.json'))
                recovery=json.loads(max(paths,key=lambda v:v.stat().st_mtime).read_text('utf8')) if paths else {}
                if not recovery.get('restored') or recovery.get('cleanup_error'):raise
            row['finished']=now();dump(journal,q)
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=300)
            q['actions'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(journal,q)
        q['status']='completed'
    finally:q['finished']=now();dump(journal,q)


if __name__=='__main__':main()
