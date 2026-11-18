"""Sequential Nov17 continuation, using exact Nov13 images and fresh evidence."""
import json
import sys
import shutil
import traceback
import manual_delivery_fix_context_20261113 as ctx

g=ctx.g
R=ctx.R
DAY=R/'测试证据/续测_20261117'
DAY.mkdir(exist_ok=True)
for module in list(sys.modules.values()):
    path=getattr(module,'__file__','') or ''
    if path.startswith(str(R/'tools')):
        for key,value in (('DAY',DAY),('D',DAY)):
            if hasattr(module,key):setattr(module,key,value)
ctx.DAY=DAY
g.runtime.RESULTS=DAY/'case_results.json'
g.runtime.REPORT=DAY/'progress.md'
for p in (R/'测试证据/手动联锁修复_20261113').glob('recover_interrupted_v1058_*.json'):
    if not (DAY/p.name).exists():shutil.copy2(p,DAY/p.name)


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('audit','manual','automatic','ai'))
    action=parser.parse_args().action
    snapshot=DAY/'drivers'/g.time.strftime('%H%M%S')
    snapshot.mkdir(parents=True,exist_ok=False)
    for name in ('resume_bench_20261117.py','gap_cases_20261113.py','gap_capture_20261113.py','manual_gate_automatic_20261113.py'):
        shutil.copy2(R/'tools'/name,snapshot/name)
    q=dict(started=g.now(),action=action,profile='BENCH_ONLY_3S',
           versions=g.runtime.EXPECTED,driver_hashes={p.name:g.runtime.sha(p) for p in snapshot.iterdir()})
    path=DAY/('action_'+action+'_'+g.time.strftime('%H%M%S')+'.json')
    g.dump(path,q)
    try:
        if action=='audit':g.audit_module.audit('independent_audit',True)
        elif action=='manual':
            import gap_cases_20261113 as cases
            cases.DAY=DAY
            try:cases.manual(include_second_fan=True,require_indoor_alarm=True)
            finally:g.audit_module.audit('after_manual',True)
        elif action=='automatic':
            import manual_gate_automatic_20261113 as cases
            cases.ctx=ctx;cases.g=g
            try:cases.run()
            finally:g.audit_module.audit('after_automatic',True)
        elif action=='ai':
            import gap_cases_20261113 as cases
            cases.DAY=DAY
            try:cases.ai_diagnostics()
            finally:g.audit_module.audit('after_ai',True)
        q['execution_finished']=True
    except BaseException:
        q['error']=traceback.format_exc();raise
    finally:
        q['finished']=g.now();g.dump(path,q)


if __name__=='__main__':main()
