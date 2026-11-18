"""Continue normal-protocol board tests after the active special-stage queue.

This process does not open COM6 until the exact predecessor journal is finished
and its last board batch has restored parameters. All actions use one writer.
Pause requests cause normal cleanup before exiting, not abandoned board state.
"""
from v1055_bench_context_20261109 import *
from remaining_pid_live_20261106 import *
from continuous_special_stages_v1055_20261109 import PAUSE,paused

BaseHeatBench=HeatBench
class CheckedBench(BaseHeatBench):
    def snapshot(self,label):
        if not getattr(self,'_cleaning_up',False):paused()
        return super().snapshot(label)
    def finish(self):
        self._cleaning_up=True
        return super().finish()

def cold_config(b,mode):
    b.setup(mode)
    b.config({128:0,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
        160:320,161:150,315:0,320:0,346:0,245:1,247:0,
        329:2,330:0,331:1,335:1,336:1,337:1,338:1,328:0,132:0,135:0})

def mode_matrix():
    import continuous_mode_matrix_v1055_20261109 as m
    m.HeatBench=CheckedBench
    m.main()

def one_stage():
    b=CheckedBench('continuous_single_stage_auto')
    try:
        for disinfect,exhaust,cid in ((1,0,'T13-043'),(0,1,'T13-044')):
            e=dict(passed=False,runs=[],mode=5,scope='Auto mode with only one nonzero stage; both after policies, real clock')
            b.log['cases'][cid]=e;b.save()
            for after in (0,1):
                cold_config(b,2);b.reset_faults();b.start();b.stop()
                b.config({323:disinfect,324:exhaust,325:after,236:5})
                run=dict(after=after,passed=False,edges=[]);e['runs'].append(run);b.save()
                b.wr(398,1);began=time.monotonic();last=None;heartbeat=began;seen=set();active_seen=False
                intended=3 if disinfect else 4
                phase_started=None;phase_last=None;actuator_samples=0;output_gap=None
                while True:
                    s=b.snapshot('single-stage automatic sequence');diag=b.rd(885,3);mode=b.rd(236)[0]
                    s.update(special_diag=diag,mode=mode);phase=diag[0]
                    if phase in (1,2,3,4,5,6):seen.add(phase)
                    assert not any(s['faults']),s
                    assert all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
                    assert all(v not in (2,3,4) for pair in s['outdoor_status'] for v in pair),s
                    if phase==intended:
                        observed=time.monotonic()
                        if phase_started is None:phase_started=observed
                        phase_last=observed
                        correct=(s['do'][3] and s['do'][10] and not s['do'][8]) if disinfect else (s['do'][3] and s['do'][8] and not s['do'][10])
                        if correct:
                            actuator_samples+=1;active_seen=True;output_gap=None
                        else:
                            if output_gap is None:output_gap=observed
                            assert observed-output_gap<1,('persistent active-phase output mismatch',s)
                    if disinfect:assert 4 not in seen and 5 not in seen,seen
                    else:assert 3 not in seen and 5 not in seen,seen
                    marker=(mode,s['state'][9],phase,tuple(s['do']))
                    if marker!=last or time.monotonic()-heartbeat>=30:
                        run['edges'].append(s);b.save();last=marker;heartbeat=time.monotonic()
                        print('SINGLE AUTO',cid,after,round(time.monotonic()-began,1),mode,diag,flush=True)
                    complete=active_seen and (
                        after==0 and s['state'][9]==0 and phase==0 and loads_off(s) or
                        after==1 and mode==2 and s['state'][9]==2 and phase==0 and s['do'][3] and s['do'][8])
                    if complete:
                        assert phase_started is not None and phase_last-phase_started>=58.5,('active stage too short',phase_started,phase_last)
                        assert actuator_samples>=20,('insufficient actual actuator evidence',actuator_samples)
                        run.update(final=s,active_observed_s=phase_last-phase_started,actuator_samples=actuator_samples)
                        break
                    assert time.monotonic()-began<360,(cid,'single stage timeout',s)
                    time.sleep(.2)
                run.update(passed=True,phases=sorted(seen),duration_s=time.monotonic()-began);b.save();b.stop()
            e['passed']=True
            b.record_local(cid,True,f'V10.55自动模式消毒/排毒时间={disinfect}/{exhaust}分钟，结束选择0和1均实际完整运行；只进入有效阶段，结束停机或返回先前通风，未启动无效阶段、压机及热湿输出。真实150/20秒及分钟计时；端子/消毒效果/正式档另验。',e)
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()

def maximum_times():
    b=CheckedBench('continuous_special_maximum_time')
    try:
        cold_config(b,5);runs=[]
        for address in (323,324):
            points=[]
            for value in (0,1,998,999):
                b.wr(address,value);got=b.rd(address)[0];assert got==value
                points.append(dict(requested=value,readback=got,at=now()))
            b.c.write_single_register(1,address,1000);time.sleep(.3)
            overflow=b.rd(address)[0]
            assert overflow<=999,('time upper bound accepted overflow',address,overflow)
            runs.append(dict(address=address,legal_points=points,overflow_request=1000,overflow_readback=overflow))
            b.wr(address,1)
        e=dict(passed=True,runs=runs,scope='Parameter readback/range only;999-minute execution not performed')
        b.record_local('T13-046',True,'V10.55消毒/排毒时长各实写0、1、998、999并回读，越界1000请求未保留为超过999的值。仅参数范围核对；999分钟完整运行与边界计时未实跑，仍待长时条件。',e)
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()

def cycles():
    b=CheckedBench('continuous_thirty_normal_cycles')
    try:
        e=dict(passed=False,runs=[],scope='Thirty normal BENCH cycles, no thermal load; runtime/terminal production checks separate')
        b.log['cases']['T13-063']=e;b.save()
        for mode in (2,0,1):
            cold_config(b,mode);b.config({330:2,328:30,132:30,135:30})
            for i in range(10):
                paused();started=time.monotonic();run=dict(mode=mode,round=i+1,started=now(),passed=False);e['runs'].append(run)
                s=b.start();assert s['do'][3]==s['do'][6]==s['do'][8]==1,s
                assert b.rd(2622,18)==runtime.EXPECTED and b.rd(119)[0]==0
                assert all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
                run['running']=s;time.sleep(1)
                s=b.stop();assert loads_off(s) and b.rd(119)[0]==0
                run.update(stopped=s,passed=True,duration_s=time.monotonic()-started);b.save()
                print('NORMAL CYCLE',len(e['runs']),'/30',mode,i+1,round(run['duration_s'],2),flush=True)
        assert len(e['runs'])==30
        e['passed']=True
        b.record_local('T13-063',True,'V10.55 BENCH通风/制冷/制热各10轮、合计30轮普通启停完成；逐轮核对三风机运行、正常停止、负载软件输出清零、压机反馈为0及三板版本；无热湿负载。满载压机循环、实际端子与正式时序另验。',e)
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()

def soak():
    b=CheckedBench('continuous_real_two_hour_monitor')
    session=None
    try:
        cold_config(b,2);b.config({330:2,328:30,132:30,135:30});b.reset_faults();b.start()
        session=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        session.open();target=session.target
        e=dict(passed=False,segments=[],mode=2,started=now(),scope='Two real hours in ventilation; software outputs/versions and read-only uptime; no PID/real thermal stability claim')
        b.log['cases']['T13-064']=e
        trace=D/('continuous_soak_samples_20261109_'+time.strftime('%H%M%S')+'.ndjson');assert not trace.exists();e['trace_file']=trace.relative_to(R).as_posix()
        start=time.monotonic();last_uptime=None
        with trace.open('w',encoding='utf8',buffering=1) as f:
            for name,duration,period in (('baseline20min',1200,1),('monitor40min',2400,.15),('baseline60min',3600,1)):
                segment=dict(name=name,requested_s=duration,post_response_wait_s=period,samples=0,started=now());e['segments'].append(segment)
                began=time.monotonic();heartbeat=began
                while time.monotonic()-began<duration:
                    s=b.snapshot('soak '+name);b.log['samples'].pop()
                    uptime=target.read32(b.sy['Systick_1ms'][0]);s['uptime_low32']=uptime
                    if last_uptime is not None:assert (uptime-last_uptime)&0xffffffff<10000,('possible reset/long sampling gap',last_uptime,uptime)
                    last_uptime=uptime
                    assert not any(s['faults']) and s['state'][9]==2,s
                    assert all(s['do'][i] for i in (3,6,8)) and all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
                    assert b.rd(2622,18)==runtime.EXPECTED
                    s.update(total_elapsed_s=time.monotonic()-start,segment=name)
                    f.write(json.dumps(s,ensure_ascii=False)+'\n');segment['samples']+=1
                    if time.monotonic()-heartbeat>=30:
                        segment['elapsed_s']=time.monotonic()-began;b.save();heartbeat=time.monotonic()
                        print('REAL SOAK',name,round(time.monotonic()-start,1),segment['samples'],flush=True)
                    time.sleep(min(period,max(.001,duration-(time.monotonic()-began))))
                segment.update(elapsed_s=time.monotonic()-began,passed=True);b.save()
        e.update(elapsed_s=time.monotonic()-start,passed=True);assert e['elapsed_s']>=7200
        b.record_local('T13-064',True,f'V10.55通风真实连续{e["elapsed_s"]:.1f}秒，20分钟基线/40分钟高读频/60分钟基线；逐样本记录版本、故障、风机输出、只读系统运行时钟，未观察到复位或输出异常。NDJSON原始轨迹留存；本例未覆盖热工闭环、PID细粒度漂移、实际端子及长期老化。',e)
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        if session:session.close()
        b.finish()

def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);args=p.parse_args()
    dependency=args.after if args.after.is_absolute() else R/args.after
    journal=D/('continuous_followups_queue_20261109_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),single_writer=True,dependency=dependency.relative_to(R).as_posix(),actions=[]);dump(journal,q)
    heartbeat=time.monotonic()
    while True:
        paused();previous=json.loads(dependency.read_text('utf8'))
        if previous.get('finished'):break
        if time.monotonic()-heartbeat>=30:
            print('FOLLOWUPS WAIT PREDECESSOR',previous['groups'][-1]['name'],flush=True);heartbeat=time.monotonic()
        time.sleep(2)
    q['predecessor_finished']=now();dump(journal,q)
    from continuous_reverse_commands_v1055_20261109 import reverse_commands
    actions=(('reverse-commands',reverse_commands),('mode-matrix',mode_matrix),('single-stage-auto',one_stage),('maximum-times',maximum_times),('thirty-cycles',cycles),('two-hour-monitor',soak))
    for name,fn in actions:
        paused();row=dict(name=name,status='running',started=now());q['actions'].append(row);dump(journal,q)
        try:
            fn();row['status']='completed'
        except InterruptedError:
            row.update(status='paused',error=traceback.format_exc());dump(journal,q);return
        except Exception:
            row.update(status='failed_or_unavailable',error=traceback.format_exc());dump(journal,q)
            latest=max(D.glob('remaining571_heat_dynamic_continuous_*.json'),key=lambda p:p.stat().st_mtime)
            d=json.loads(latest.read_text('utf8'))
            if not d.get('restored') or d.get('cleanup_error'):raise
        row['finished']=now();dump(journal,q)
    q['finished']=now();dump(journal,q);print('FOLLOWUPS COMPLETE',journal,flush=True)

if __name__=='__main__':main()
