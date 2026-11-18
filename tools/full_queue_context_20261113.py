"""Exact V10.61/V12.43 binding for authorized Nov13 bench; import is read-only."""
import sys
import full_queue_context_20261112 as prior
from full_queue_context_20261112 import *

DAY = R / '测试证据/逐项测试_20261113'
DAY.mkdir(parents=True, exist_ok=True)
I = R / '.codex-tmp/ambient_scope_v1061_20261112/BENCH_ONLY_3S'
LIMITS = '330 V10.61 /316 V12.43 BENCH; board input simulation/software readback; physical terminals and formal timing separate'
runtime.I = I
runtime.D = DAY
runtime.RESULTS = DAY / 'case_results.json'
runtime.REPORT = R / '逐项测试进度_20261113.md'
runtime.EXPECTED[:] = [330,10,61,2026,11,12,316,12,43,2026,11,12,316,12,43,2026,11,12]
runtime.BOARDS[:] = [tuple([*b[:-1], b[-1].replace('10.60','10.61')]) for b in runtime.BOARDS]
BOARDS = runtime.BOARDS
module = prior
seen = set()
while id(module) not in seen:
    seen.add(id(module))
    module.DAY = module.D = DAY
    module.I = I
    module.LIMITS = LIMITS
    if not hasattr(module, 'prior'):
        break
    module = module.prior
import heat_dynamic_board_20261106 as heat
heat.I = I
heat.D = DAY
heat.BOARDS = BOARDS
for name in ('full_queue_context_20261112','joint_v1060_context_20261112',
             'joint_v1242_context_20261112','joint_v1059_context_20261112',
             'joint_v1058_context_20261111','v1055_bench_context_20261109',
             'joint_v1056_context_20261110'):
    sys.modules[name] = sys.modules[__name__]
import joint_precondition_20261110 as precondition
precondition.DAY = DAY
precondition.I = I
precondition.BOARDS = BOARDS


def current_bench_class():
    import joint_priority_20261110 as priority
    priority.DAY = DAY
    Base = prior.current_bench_class()
    class CurrentBench(Base):
        def __init__(self, name):
            super().__init__(name)
            self.log.update(current_package=str(I.relative_to(R)), limitations=LIMITS)
            self.log['current_driver_sha256']={p.relative_to(R).as_posix():runtime.sha(p)
                for p in sorted((R/'tools').glob('*20261113.py'))}
            assert self.rd(2622,18) == runtime.EXPECTED, 'Wrong bench firmware'
            assert self.rd(1299) == [15107], 'Wrong bench timing profile'
            self.save()
    return CurrentBench
