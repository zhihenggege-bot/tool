"""Environmental full-load order, three actual starts, single-writer follow-on."""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench,paused
import subprocess,sys


def run(cooling):
    mode=0 if cooling else 1;cid='T09-021' if cooling else 'T09-022'
    b=CheckedBench('environment_full_order_'+('cool' if cooling else 'heat'))
    e=dict(passed=False,runs=[],scope='Three actual full-load feedback sequences; BENCH; no physical compressor power')
    b.log['cases'][cid]=e;b.save()
    try:
        raw=signed16(b.rd(512)[0])-signed16(b.rd(493)[0]);target=350 if cooling else 0
        if not -100<=target-raw<=100:
            e.update(skipped=True,reason='Default full-load temperature unreachable with legal NTC2 calibration',
                     raw_temp10=raw,required_offset10=target-raw,legal_offset10=[-100,100])
            b.save();print('ENV FULL SKIP',cid,e['reason'],flush=True);return
        for trial in range(1,4):
            paused();b.setup(mode)
            b.config({315:1,327:1,128:1,127:0,332:0,333:0,334:0,
                125:0,126:0,248:0,245:1,247:0,316:350,317:220,318:0,319:120,
                329:2,330:0,331:0,346:0,320:0,30:0,12:500})
            b.temperature(0,250);b.temperature(2,target);b.reset_faults()
            assert b.rd(2678)[0]==4 and b.rd(2622,18)==runtime.EXPECTED
            initial=b.snapshot('full-load order initial stopped')
            assert initial['state'][9]==0 and all(v==0 for pair in initial['outdoor_status'] for v in pair)
            r=dict(round=trial,started=now(),initial=initial,samples=[],rising_edges=[],passed=False)
            e['runs'].append(r);b.save();b.wr(398,1);began=time.monotonic();prior=set();last=None;heartbeat=began
            while True:
                paused();s=b.snapshot('full-load order startup');s.update(elapsed_s=time.monotonic()-began,
                    fresh_temp10=signed16(b.rd(512)[0]),target_count=b.rd(881)[0],
                    actual_count=b.rd(119)[0],environment_state=b.rd(882)[0])
                r['samples'].append(s)
                assert not any(s['faults']),('unexpected fault',s)
                assert all(s['ao'][i]==0 for i in (0,1,2,8,9)),('unexpected thermal/humidity AO',s)
                active={(i+1,j+1) for i,pair in enumerate(s['outdoor_status']) for j,v in enumerate(pair) if v in (2,3,4)}
                assert prior<=active,('running compressor disappeared during full-load startup',prior,active,s)
                newly=active-prior
                for unit,comp in sorted(newly):
                    r['rising_edges'].append(dict(unit=unit,compressor=comp,t=s['monotonic'],elapsed_s=s['elapsed_s']))
                # One sample containing two new compressors cannot establish
                # their order; preserve it and mark incomplete rather than sort
                # the sample into an invented startup sequence.
                if len(newly)>1:r.setdefault('ambiguous_edges',[]).append(dict(new=sorted(newly),snapshot=s))
                marker=(s['state'][9],tuple(tuple(p) for p in s['outdoor_status']))
                if marker!=last or time.monotonic()-heartbeat>=25:
                    print('ENV FULL',cid,trial,round(s['elapsed_s'],1),s['outdoor_status'],'target',s['target_count'],flush=True)
                    last=marker;heartbeat=time.monotonic();b.save()
                prior=active
                if len(active)==4:
                    r['full_load']=s;break
                assert time.monotonic()-began<240,('full load unavailable within timeout',s)
                time.sleep(.15)
            order=[x['unit'] for x in r['rising_edges']]
            edges=r['rising_edges'];gaps=[edges[i]['elapsed_s']-edges[i-1]['elapsed_s'] for i in range(1,len(edges))]
            r.update(order_by_unit=order,observed_gaps_s=gaps,duration_s=time.monotonic()-began)
            r['passed']=order==[1,1,2,2] and not r.get('ambiguous_edges') and r['full_load']['target_count']==4
            b.save();r['stopped']=b.stop();b.save()
            assert r['passed'],(cid,'order mismatch or incomplete sample resolution',r['order_by_unit'])
        e['passed']=len(e['runs'])==3 and all(r['passed'] for r in e['runs'])
        b.record_local(cid,e['passed'],
            f'V10.55 BENCH环温'+('制冷35℃' if cooling else '制热0℃')+
            '默认满载端点，正常启停三轮，四压机运行反馈逐个建立；每轮外机顺序均为1/1/2/2，同机压机不强定编号，保留各次反馈时间间隔。合法校准，无需求/输出/计时RAM写入；不等同正式30秒、真实压机动力或物理端子。',e)
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    dependency=a.after.resolve();journal=D/('continuous_env_full_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),dependency=dependency.relative_to(R).as_posix(),status='waiting_without_hardware',actions=[]);dump(journal,q)
    while True:
        paused()
        try:prior=json.loads(dependency.read_text('utf8'))
        except (OSError,ValueError):prior={}
        if prior.get('finished'):break
        time.sleep(5)
    if prior.get('status')!='completed':
        q.update(status='predecessor_not_completed_no_hardware',finished=now());dump(journal,q);return
    checks=list(D.glob('independent_final_readback_20261109_*.json'))
    check=json.loads(max(checks,key=lambda v:v.stat().st_mtime).read_text('utf8')) if checks else {}
    if not check.get('passed'):
        q.update(status='predecessor_final_readback_not_passed_no_hardware',finished=now());dump(journal,q);return
    q['status']='running';dump(journal,q)
    try:
        for cooling in (True,False):
            row=dict(cooling=cooling,started=now());q['actions'].append(row);dump(journal,q)
            try:run(cooling);row['status']='finished_see_actual_scope'
            except Exception:
                row.update(status='failed_or_unavailable',error=traceback.format_exc())
                paths=list(D.glob('remaining571_heat_dynamic_environment_full_order_'+('cool' if cooling else 'heat')+'_*.json'))
                restored=json.loads(max(paths,key=lambda v:v.stat().st_mtime).read_text('utf8')) if paths else {}
                if not restored.get('restored') or restored.get('cleanup_error'):raise
            row['finished']=now();dump(journal,q)
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=300)
            q['actions'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(journal,q)
        q['status']='completed'
    finally:q['finished']=now();dump(journal,q)


if __name__=='__main__':main()
