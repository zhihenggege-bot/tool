"""Bind only follow-up verification to330 V10.60 /316 V12.43 exact images."""
import sys
import joint_v1242_context_20261112 as prior
from joint_v1242_context_20261112 import *

DAY=R/'测试证据/四项复核_20261112/restart_fix'
DAY.mkdir(exist_ok=True)
I=R/'.codex-tmp/restart_guard_v1060_v1243_20261112/BENCH_ONLY_3S'
runtime.I=I;runtime.D=DAY
runtime.RESULTS=DAY/'case_results.json'
runtime.REPORT=R/'四项复核修复复测进度_20261112.md'
runtime.EXPECTED[:]=[330,10,60,2026,11,12,316,12,43,2026,11,12,316,12,43,2026,11,12]
runtime.BOARDS[:]=[tuple([*b[:-1],b[-1].replace('10.59','10.60').replace('12.42','12.43')]) for b in runtime.BOARDS]
BOARDS=runtime.BOARDS
LIMITS='330 V10.60 /316 V12.43 BENCH；正常接口与输入模拟、软件输出回读；非物理端子/正式时序验收'
import heat_dynamic_board_20261106 as heat
heat.I=I;heat.D=DAY;heat.BOARDS=BOARDS
for name in ('joint_v1242_context_20261112','joint_v1059_context_20261112',
             'joint_v1058_context_20261111','v1055_bench_context_20261109','joint_v1056_context_20261110'):
    sys.modules[name]=sys.modules[__name__]


def current_bench_class():
    import joint_priority_20261110 as priority
    Base=prior.current_bench_class()
    priority.DAY=DAY
    class CurrentBench(Base):
        def __init__(self,name):
            super().__init__(name)
            self.log.update(current_package=str(I.relative_to(R)),limitations=LIMITS,
                            versions=self.rd(2622,18))
            self.save()
    return CurrentBench
