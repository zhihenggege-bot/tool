"""Bind all helpers to exact V10.63/V12.46 images and fresh fix evidence."""
import manual_delivery_fix_context_20261113 as previous
from manual_delivery_fix_context_20261113 import *

DAY=R/'测试证据/单变频降载修复_20261117/最低频默认30Hz_V12.46'
DAY.mkdir(parents=True,exist_ok=True)
I=R/'.codex-tmp/vfd_unload_min30_v1063_v1246_20261117/BENCH_ONLY_3S'
g.runtime.EXPECTED[:]=[330,10,63,2026,11,13,316,12,46,2026,11,17,316,12,46,2026,11,17]
g.BOARDS[:]=[tuple([*b[:-1],b[-1].replace('12.44','12.46')]) for b in g.BOARDS]
for module in list(sys.modules.values()):
    path=getattr(module,'__file__','') or ''
    if path.startswith(str(R/'tools')):
        for k,v in (('I',I),('DAY',DAY),('D',DAY),('LIMITS','330 V10.63 /316 V12.46 BENCH; software/input evidence')):
            if hasattr(module,k):setattr(module,k,v)
g.runtime.RESULTS=DAY/'case_results.json';g.runtime.REPORT=DAY/'progress.md'
for p in (R/'测试证据/手动联锁修复_20261113').glob('recover_interrupted_v1058_*.json'):
    if not (DAY/p.name).exists():g.shutil.copy2(p,DAY/p.name)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('audit','automatic'));a=parser.parse_args()
    if a.action=='audit':g.audit_module.audit('independent_audit',True)
    else:
        import manual_gate_automatic_20261113 as cases
        cases.ctx=sys.modules[__name__];cases.g=g
        try:cases.run()
        finally:g.audit_module.audit('after_automatic',True)
