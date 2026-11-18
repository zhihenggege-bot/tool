"""Deploy isolated guard/recovery corrections, then run a scoped follow-up."""
import joint_v1060_context_20261112 as ctx
from joint_v1060_context_20261112 import *
import argparse
import continuous_special_stages_v1055_20261109 as pause_module
pause_module.PAUSE=R/'.codex-tmp/four_followups_pause.request'


def audit(label='restart_fix_audit',image=False):
    import bench_current_20261112 as common
    common.DAY=DAY;common.I=I;common.BOARDS=BOARDS
    return common.audit(label,image)


def deploy():
    c=runtime.client()
    try:
        versions=c.read_holding_registers(1,2622,18)
        assert versions==[330,10,59,2026,11,11,316,12,42,2026,11,12,316,12,42,2026,11,12]
        snapshot=runtime.snap(c)
        assert c.read_holding_registers(1,398,1)==[0]
        assert snapshot['state'][9]==0 and loads_off(snapshot)
    finally:c.close()
    m=json.loads((I/'manifest.json').read_text('utf8'))
    assert all(runtime.sha(R/p)==h for p,h in m['source_inventory'].items())
    assert all(runtime.sha(I/p)==h for p,h in m['artifacts'].items())
    assert not (DAY/'preflight.json').exists()
    dump(DAY/'preflight.json',dict(at=now(),versions_before=versions,snapshot=snapshot,
        scope='330 watchdog and316 typeII recovery corrections;fixed50Hz AO retained',source_inventory=m['source_inventory']))
    runtime.result=lambda *a,**k:None
    runtime.flash()
    audit('post_guard_flash_audit',True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('deploy','audit','minrun','stable-lp'))
    p.add_argument('--value',type=int,choices=(60,120),default=60);a=p.parse_args()
    pause_module.paused()
    if a.action=='deploy':deploy()
    elif a.action=='audit':audit(image=True)
    elif a.action=='minrun':
        import bench_restart_diagnostics_20261112 as test
        test.run(a.value,pairs=((2,4),),initial_hold_seconds=0,require_both=True)
        audit('after_minrun_'+str(a.value)+'_audit')
    else:
        import bench_low_pressure_stable_20261112 as test
        test.run();audit('after_stable_lp_audit')
