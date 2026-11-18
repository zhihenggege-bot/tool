"""Previously untested running-stage manual/fire abort and restart checks."""
from v1055_bench_context_20261109 import *
from remaining_pid_live_20261106 import *

def main():
    b=HeatBench('special_running_abort_v1055')
    b.log['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        for mode,cid in ((3,'T13-049'),(4,'T13-053'),(5,'T13-057')):
            entry=dict(passed=False,mode=mode,runs=[],scope='Manual/fire abort in active disinfect or exhaust timer; restart resets counters; auto mode disinfect phase only')
            b.log['cases'][cid]=entry;b.save()
            b.setup(mode)
            b.config({329:2,330:0,331:1,335:1,336:1,337:1,338:1,
                      323:1,324:1,325:1,128:0,127:0,332:0,333:0,334:0,
                      245:1,247:0,125:0,126:0,248:0})
            for kind in ('manual','fire'):
                b.reset_faults();b.start()
                wait_since=time.monotonic();last=None;last_report=wait_since
                while True:
                    s=b.snapshot('establish active special timer')
                    d=b.rd(885,3);phase,count,exhaust=d
                    marker=(phase,s['do'][3],s['do'][8],s['do'][10])
                    if marker!=last or time.monotonic()-last_report>=30:
                        print('SPECIAL RUN WAIT',mode,kind,round(time.monotonic()-wait_since,1),'phase',phase,'counts',count,exhaust,flush=True)
                        b.save();last=marker;last_report=time.monotonic()
                    assert not any(s['faults']),s
                    actual_count=exhaust if mode==4 else count
                    active=(phase==(4 if mode==4 else 3) and
                            (s['do'][3]==1 and s['do'][8]==1 and s['do'][10]==0 if mode==4 else s['do'][3]==1 and s['do'][10]==1))
                    if active and actual_count>=6:
                        before=s;before.update(special_phase=phase,disinfect_count=count,exhaust_count=exhaust);break
                    assert time.monotonic()-wait_since<210,('special run unavailable',mode,phase,s)
                    time.sleep(.25)
                e=dict(kind=kind,before=before,passed=False,samples=[]);entry['runs'].append(e);b.save()
                began=time.monotonic()
                if kind=='manual':b.wr(398,0)
                else:
                    original=b.rd(156)[0];e['original_polarity']=original;b.wr(156,1-original)
                stopped=b.wait('active special abort fully stopped',lambda s:s['state'][9]==0 and loads_off(s) and b.rd(885)[0]==0,60,allow_fault=kind=='fire')
                e.update(stopped=stopped,stop_observed_s=time.monotonic()-began,special_phase_after_stop=b.rd(885)[0])
                if kind=='fire':
                    assert b.rd(605)[0]==1
                    b.wr(156,original);time.sleep(.5);assert b.rd(605)[0]==1
                    b.reset_faults()
                hold=time.monotonic()
                while time.monotonic()-hold<10:
                    s=b.snapshot('special abort no unintended restart');s['special_phase']=b.rd(885)[0];e['samples'].append(s)
                    assert s['state'][9]==0 and loads_off(s) and s['special_phase']==0 and not any(s['faults']),s
                    time.sleep(.3)
                # A genuine new startup must reset both prior elapsed counters.
                b.start();restart=b.snapshot('fresh special cycle counters reset')
                counters=b.rd(885,3)
                assert counters==[1,0,0] and not any(restart['do'][i] for i in (3,8,10)),(counters,restart)
                e.update(restart=restart,restart_diagnostics=counters,passed=True,finished=now());b.save()
                print('SPECIAL RUN ABORT PASS',mode,kind,'phase now',counters,flush=True)
                # Leave the freshly restarted wait cycle running for the next
                # fire test; do not pretend it already reached the active phase.
                if kind=='fire':b.stop()
            entry['passed']=True
            b.record_local(cid,True,f'V10.55模式{mode}：实际完成150秒开阀及相应风机等待，计时至少6秒后分别手动停机、消防DI极性模拟；步骤0、负载软件输出及[885]归零，排故复位后10秒无自行重启；每次重新开机都读到[885..887]=[1,0,0]，未沿用旧计时。'+('自动模式本例仅消毒运行阶段，排毒阶段另测。' if mode==5 else '')+'实际接点/端子、正式档待验。',entry)
            # Regression of the preceding V10.54 restart fix, here scoped to
            # the valve-wait stage. The old loaded-stage evidence is retained.
            b.start();remote_before=b.snapshot('remote stop during valve wait')
            assert b.rd(885,3)==[1,0,0]
            original=b.rd(157)[0];began=time.monotonic();b.wr(157,1-original)
            remote_stop=b.wait('remote wait-stage full stop',lambda s:s['state'][9]==0 and loads_off(s) and b.rd(885)[0]==0,20)
            b.wr(157,original)
            remote_after=b.wait('remote input restores new wait cycle',lambda s:s['state'][9]==2 and b.rd(885,3)==[1,0,0],15)
            remote=dict(passed=True,mode=mode,kind='remote_valve_wait',before=remote_before,
                        stopped=remote_stop,restarted=remote_after,duration_s=time.monotonic()-began,
                        scope='Valve-wait stage only; remote input returns without manual reset; loaded-stage V10.54 evidence separate')
            b.record_local(f'T05-{7+mode:03d}',True,f'V10.55模式{mode}阀等待阶段远程联锁断开后正常停到步骤0、[885]=0；接通后无人工复位自动重启到新阀等待，[885..887]=[1,0,0]。仅本阶段软件回归；运行负载阶段旧V10.54证据另存，端子/正式档待验。',remote)
            b.stop()
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish();print('SPECIAL RUN ABORT RESTORED',b.log.get('restored'),flush=True)

if __name__=='__main__':main()
