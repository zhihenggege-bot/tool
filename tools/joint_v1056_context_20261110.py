"""Bind legacy test helpers to the exact V10.56/V12.40 BENCH artifacts.

This module performs no hardware access. Import it before any old bench helper.
Previous version journals and firmware source remain untouched.
"""
import os
import sys
from pathlib import Path

os.environ['PSC_BENCH_PACKAGE'] = '.codex-tmp/four_outdoor_fixes_20261110'
os.environ['PSC_BENCH_INDOOR_VERSION'] = '10.56'
ROOT = Path(__file__).resolve().parents[1]
DAY = ROOT/'测试证据/修复后内外机联合实测_20261110'
DAY.mkdir(parents=True, exist_ok=True)

import run_indoor_bench_20261105 as runtime
runtime.D = DAY
runtime.RESULTS = DAY/'case_results.json'
runtime.REPORT = ROOT/'修复后内外机联合实测_20261110.md'
runtime.BOARDS[:] = [tuple(list(b[:-1])+[b[-1].replace('12.39', '12.40')])
                     for b in runtime.BOARDS]
runtime.EXPECTED[:] = [330,10,56,2026,11,10,316,12,40,2026,11,10,316,12,40,2026,11,10]
manifest = DAY/'remaining_571_manifest.json'
if not manifest.exists():
    manifest.write_bytes((ROOT/'测试证据/内机实测_20261105/BENCH_V1055_V1239/remaining_571_manifest.json').read_bytes())

from heat_dynamic_board_20261106 import *
D = DAY
LIMITS = '330 V10.56 / 316 V12.40 BENCH；板上输入模拟及软件反馈，物理端子/正式时序另验'
# All helpers importing the old selector now receive this already-bound module.
sys.modules['v1055_bench_context_20261109'] = sys.modules[__name__]


def current_bench_class():
    import joint_priority_20261110 as priority
    priority.DAY = DAY
    class CurrentBench(priority.TodayBench):
        def __init__(self, name):
            super().__init__(name)
            self.log.update(versions=self.rd(2622,18),profile=self.rd(1298,2),
                            current_package=str(I.relative_to(R)),limitations=LIMITS)
            self.save()

        def gateway(self, address, value):
            # Saved Modbus words are unsigned; the destination comparison is
            # signed for negative temperature setpoints (e.g. 316[186]).
            value=signed16(value)
            p=165+address-1830
            shared=({**{a:1331+a-170 for a in range(170,176)},
                     **{a:1337+a-179 for a in range(179,182)},
                     **{a:1389+a-182 for a in range(182,193)},193:41}).get(p)
            if shared is not None and self.rd(1319)[0]==1:
                # Error9 intentionally rejects independent gateway edits of
                # shared settings. Use the normal shared source and wait for
                # its periodic outdoor mirror instead of retrying rejection.
                self.gateway_original.setdefault(address,self.rd(address)[0])
                self.config({shared:value});began=time.monotonic()
                while True:
                    destination=signed16(self.ot.read16(self.outsy['Parameter'][0]+p*2))
                    mirror=signed16(self.rd(address)[0])
                    if destination==mirror==value:break
                    assert time.monotonic()-began<50,('shared setting did not settle',address,value,destination,mirror)
                    time.sleep(.2)
                self.log.setdefault('gateway_writes',[]).append(dict(at=now(),address=address,value=value,destination_parameter=p,destination=destination,route='normal_shared_source',source=shared))
                self.save();return
            return super().gateway(address, value)
    return CurrentBench
