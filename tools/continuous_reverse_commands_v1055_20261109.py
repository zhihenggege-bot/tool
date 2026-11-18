"""Live normal-command reversals. No demand/output/timer/fault RAM writes."""
from v1055_bench_context_20261109 import *
from remaining_pid_live_20261106 import *
from continuous_special_stages_v1055_20261109 import paused


def reverse_commands():
    from continuous_followups_v1055_20261109 import CheckedBench,cold_config
    errors=[]
    # Separate restoration per scenario: an unavailable precondition must not
    # prevent the remaining independent reversals from being exercised.
    for scenario,cid in (('valve','T13-059'),('pressure','T13-060'),('loading','T13-061'),('blowdown','T13-062')):
        b=CheckedBench('reverse_'+scenario)
        e=dict(passed=False,scenario=scenario,scope='Live ordinary commands; start during shutdown is discarded, not queued')
        b.log['cases'][cid]=e;b.save()
        try:
            cold_config(b,0 if scenario in ('loading','blowdown') else 2)
            b.config({330:0,331:0,328:0,135:0,132:0})
            if scenario=='loading':
                b.config({128:1,315:1,327:1,316:350,317:220,329:2,
                          335:0,336:0,337:0,338:0})
                b.temperature(0,250);b.temperature(2,350)
            if scenario=='pressure':
                b.config({386:2})
                if b.rd(1363)[0]!=1:b.wr(397,1-b.rd(397)[0])
                time.sleep(.4)
                assert b.rd(1363)[0]==1,('supply pressure closed precondition missing',b.rd(1363))
            b.reset_faults();b.wr(398,1)
            if scenario=='valve':
                s=b.wait('genuine normal valve wait',lambda s:s['state'][9]==1 and not s['do'][3],8)
            elif scenario=='pressure':
                s=b.wait('genuine supply pressure confirmation',lambda s:s['state'][9]==1 and s['do'][3] and b.rd(888)[0]<3,12)
                s['pressure_count']=b.rd(888)[0];s['raw_X15']=b.rd(1363)[0]
            elif scenario=='loading':
                s=b.wait('actual partial compressor loading',lambda s:s['state'][9]==2 and 0<sum(v==2 for pair in s['outdoor_status'] for v in pair)<4,160)
                e['pending_request_cancellation_scope']='Actual partial feedback only; unacknowledged transport request cancellation not independently isolated'
            else:
                s=b.wait('cooling normal running before blowdown',lambda s:s['state'][9]==2 and s['do'][3],30)
            e['before_stop']=s;b.save();b.wr(398,0)
            s=b.wait('normal shutdown established before reverse',lambda s:s['state'][9] in (3,4),10)
            e['shutdown_before_reverse']=s
            b.wr(398,1);e['reverse_written']=now();began=time.monotonic();e['shutdown_samples']=[]
            last_duplicate=began;e['duplicate_stop_commands']=[]
            while True:
                paused();s=b.snapshot('shutdown after reversed start');s['command']=b.rd(398)[0]
                e['shutdown_samples'].append(s)
                assert not any(s['faults']),s
                assert all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
                assert s['state'][9]!=2,('shutdown bypassed by reversed start',s)
                if s['state'][9]==0 and loads_off(s) and all(v not in (2,3,4) for pair in s['outdoor_status'] for v in pair):
                    e['stopped']=s;break
                if time.monotonic()-last_duplicate>=1:
                    b.wr(398,0);last_duplicate=time.monotonic()
                    e['duplicate_stop_commands'].append(dict(at=now(),elapsed_s=last_duplicate-began))
                assert time.monotonic()-began<180,('normal shutdown did not finish',s)
                time.sleep(.2)
            assert s['command']==0,('start while stopping was not cleared',s)
            hold=time.monotonic();e['hold_samples']=[]
            while time.monotonic()-hold<5:
                paused();s=b.snapshot('no queued restart');e['hold_samples'].append(s)
                assert s['state'][9]==0 and loads_off(s) and not any(s['faults']),s
                time.sleep(.25)
            if scenario=='loading':
                # Avoid reloading after the cancellation check; the fresh
                # restart here qualifies the normal command chain only.
                b.temperature(2,220)
                b.config({128:0})
            e['fresh_start']=b.start()
            e['fresh_actuators']=b.wait('fresh command establishes supply fan',lambda s:s['state'][9]==2 and s['do'][3],30)
            e['final_stop']=b.stop();assert loads_off(e['final_stop'])
            e.update(passed=True,shutdown_observed_s=time.monotonic()-began)
            b.record_local(cid,True,f'V10.55真实{scenario}阶段先正常停机，再在停机未完成时发开机；停机期间每秒重复停机指令未阻止流程收敛，命令清0、停后5秒未排队重启，完全停止后新命令可正常开机。仅软件状态/输出；加载例是实际部分压机反馈中止，不冒充独立未ACK请求取消或物理端子证据。',e)
        except InterruptedError:
            b.log['error']=traceback.format_exc();b.save();raise
        except Exception:
            e.update(error=traceback.format_exc(),completed=False);b.log['error']=e['error'];b.save()
            errors.append(dict(id=cid,error=e['error'],evidence=b.path.relative_to(R).as_posix()))
            print('REVERSE FAILED OR UNAVAILABLE',cid,e['error'].splitlines()[-1],flush=True)
        finally:
            b.finish();print('REVERSE RESTORED',cid,b.log.get('restored'),flush=True)
    if errors:raise RuntimeError(('Reverse scenarios incomplete; independent remaining scenarios were continued',errors))


if __name__=='__main__':reverse_commands()
