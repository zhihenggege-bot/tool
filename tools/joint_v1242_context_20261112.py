"""Bind only the authorized four follow-ups; whole-day queue remains paused."""
import sys
import joint_v1059_context_20261112 as prior
from joint_v1059_context_20261112 import *

DAY=R/'测试证据/四项复核_20261112'
DAY.mkdir(exist_ok=True)
I=R/'.codex-tmp/vfd_scale_v1242_20261112/BENCH_ONLY_3S'
runtime.I=I;runtime.D=DAY
runtime.RESULTS=DAY/'case_results.json';runtime.REPORT=R/'四项复核进度_20261112.md'
runtime.EXPECTED[:]=[330,10,59,2026,11,11,316,12,42,2026,11,12,316,12,42,2026,11,12]
runtime.BOARDS[:]=[tuple([*b[:-1],b[-1].replace('12.41','12.42')]) for b in runtime.BOARDS]
BOARDS=runtime.BOARDS
LIMITS='330 V10.59 / 316 V12.42 BENCH；正常接口与输入模拟、软件输出回读；非物理端子/正式时序验收'

# Imported helpers see the new exact AXFs, including spawned acquisition children.
import heat_dynamic_board_20261106 as heat
heat.I=I;heat.D=DAY;heat.BOARDS=BOARDS
for name in ('joint_v1059_context_20261112','joint_v1058_context_20261111',
             'v1055_bench_context_20261109','joint_v1056_context_20261110'):
    sys.modules[name]=sys.modules[__name__]

def current_bench_class():
    import joint_priority_20261110 as priority
    Base=prior.current_bench_class()
    priority.DAY=DAY
    class CurrentBench(Base):
        def __init__(self,name):
            super().__init__(name)
            original=self.c.read_holding_registers
            def read(slave,address,count):
                for attempt in range(4):
                    try:return original(slave,address,count)
                    except Exception as exc:
                        if not any(s in str(exc).lower() for s in ('无应答','长度不足','timeout','超时','crc')) or attempt==3:raise
                        self.log.setdefault('transient_read_retries',[]).append(dict(at=now(),address=address,count=count,error=repr(exc)))
                        self.save();time.sleep(.2)
            self.c.read_holding_registers=read
            self.log.update(current_package=str(I.relative_to(R)),limitations=LIMITS)
            self.save()
    return CurrentBench
