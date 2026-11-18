"""Bind targeted rerun helpers to V12.44, leaving historical evidence intact."""
import gap_capture_20261113 as g
import sys

R=g.R
DAY=R/'测试证据/手动联锁修复_20261113'
DAY.mkdir(parents=True,exist_ok=True)
I=R/'.codex-tmp/manual_gate_v1244_20261113/BENCH_ONLY_3S'
g.runtime.EXPECTED[:]=[330,10,61,2026,11,12,316,12,44,2026,11,13,316,12,44,2026,11,13]
g.BOARDS[:]=[tuple([*b[:-1],b[-1].replace('12.43','12.44')]) for b in g.BOARDS]
for module in list(sys.modules.values()):
    path=getattr(module,'__file__','') or ''
    if path.startswith(str(R/'tools')):
        for k,v in (('I',I),('DAY',DAY),('D',DAY),('LIMITS','330 V10.61 /316 V12.44 BENCH; normal command/input simulation; software outputs only')):
            if hasattr(module,k):setattr(module,k,v)
g.runtime.RESULTS=DAY/'case_results.json'
g.runtime.REPORT=DAY/'progress.md'
for p in (R/'测试证据/缺口复测_20261113').glob('recover_interrupted_v1058_*.json'):
    if not (DAY/p.name).exists():g.shutil.copy2(p,DAY/p.name)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action');a=p.parse_args()
    if a.action=='audit':g.audit_module.audit('independent_audit',True)
    elif a.action=='manual':
        import gap_cases_20261113 as cases
        cases.DAY=DAY
        try:cases.manual(include_second_fan=True)
        finally:g.audit_module.audit('after_manual',True)
    else:raise ValueError(a.action)
