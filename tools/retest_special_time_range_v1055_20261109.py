"""Boundary retry after the existing continuous queue and its final verifier.

The firmware silently rejects invalid HMI writes. Catch that protocol outcome
only while also checking the previous value, live versions and a legal write.
An arbitrary communication failure is not counted as successful rejection.
"""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench,cold_config


def test():
    b=CheckedBench('special_time_range_retest')
    e=dict(passed=False,runs=[],earlier_attempt_retained=True,
           scope='Time parameter readback only;999-minute actual execution not performed')
    b.log['cases']['T13-046']=e;b.save()
    try:
        cold_config(b,5)
        for address in (323,324):
            run=dict(address=address,legal=[],invalid=[]);e['runs'].append(run);b.save()
            for value in (0,1,998,999):
                b.wr(address,value)
                got=b.rd(address)[0];assert got==value
                run['legal'].append(dict(requested=value,readback=got,at=now()));b.save()
            for value in (1000,65535):
                b.wr(address,999);prior=b.rd(address)[0]
                row=dict(requested_unsigned=value,prior=prior,at=now());run['invalid'].append(row);b.save()
                try:
                    b.c.write_single_register(1,address,value)
                    row['write_response']='normal response'
                except Exception as exc:
                    row.update(write_exception=repr(exc),write_response='no response or protocol rejection; verify actual state next')
                # Recovery reads must succeed; silence alone cannot pass.
                row['readbacks']=[b.rd(address)[0] for _ in range(3)]
                row['versions']=b.rd(2622,18)
                assert row['versions']==runtime.EXPECTED
                assert row['readbacks']==[prior]*3,('out of range write changed value',row)
                b.wr(address,1);row['legal_write_after']=b.rd(address)[0]
                assert row['legal_write_after']==1
                row['passed']=True;b.save()
            run['passed']=True;b.save()
        e['passed']=True
        b.record_local('T13-046',True,'V10.55消毒/排毒时长各实写0、1、998、999均正确回读；非法1000及-1请求按当前协议拒写，每次连续3次回读保留原值999、三板版本正常，随后合法1可写可读。原首次无应答中断证据保留，非固件修复。仅参数范围，不声称实际运行999分钟。',e)
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    dependency=a.after.resolve()
    journal=D/('time_range_retry_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),dependency=dependency.relative_to(R).as_posix(),status='waiting_without_hardware');dump(journal,q)
    while True:
        from continuous_special_stages_v1055_20261109 import paused
        paused()
        try:d=json.loads(dependency.read_text('utf8'))
        except (OSError,ValueError):d={}
        if d.get('finished'):
            if not d.get('independent_readback_passed'):
                q.update(status='predecessor_recovery_not_confirmed_no_hardware_access',finished=now());dump(journal,q);return
            break
        time.sleep(5)
    q.update(status='running',started_test=now());dump(journal,q)
    try:test();q['status']='completed'
    except BaseException:q.update(status='failed',error=traceback.format_exc());raise
    finally:q['finished']=now();dump(journal,q)


if __name__=='__main__':main()
