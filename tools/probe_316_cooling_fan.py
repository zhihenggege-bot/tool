"""盯 316 的**制冷**风机状态机 —— 变频（类型2/4）和 4 段（类型3）。

用途：
  1. 验 V12.10 的两条改动
     A 变频风机减到最低频为止、不停机（有压机运行时不允许 OutdoorVfdOn 掉 0）
     B 加减载动态化：冷凝 >36.0 每秒加、<34.0 每秒减，中间保持（不再等 30 秒）
  2. 验规格书「一定一双速」的 4 段控制
     段1 单速关+双速低速 / 段2 单速+双速关 / 段3 单速+双速低速 / 段4 单速+双速高速

只读，attach 模式（绝不停核）。跑法：
    python.exe tools/probe_316_cooling_fan.py [秒数] [每几秒打一行,默认2]
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PARAM_BASE = 0x2000164A          # int16_t Parameter[ParameterSize]

# ---- .axf 符号表核对过的绝对地址 ----
A_STAGE = 0x20000D00       # unsigned char OutdoorFanStage
A_VFD_ON = 0x20000D01      # unsigned char OutdoorVfdOn
A_FIXED_ON = 0x20000D02    # unsigned char OutdoorFixedOn
A_II_HIGH = 0x20000D06     # unsigned char OutdoorTypeIIFan2High
A_II_DEAD = 0x20000D07     # unsigned char OutdoorTypeIIFan2SwapDead
A_II_STAGE = 0x20000D08    # unsigned char OutdoorTypeIIStage
A_II_PEND = 0x20000D09     # unsigned char OutdoorTypeIIPendingStage
A_II_LOWOFF = 0x20000D0B   # unsigned char OutdoorTypeIILowFanOff
A_CHGSEC = 0x20000D28      # unsigned int  OutdoorFanChangeSeconds
A_VFD_SPEED = 0x20000D30   # unsigned int  OutdoorVfdSpeed (0.1Hz)
A_VFD_LOAD = 0x20000D48    # unsigned int  OutdoorVfdLoadCount
A_VFD_UNLOAD = 0x20000D4C  # unsigned int  OutdoorVfdUnloadCount
A_VFD_FULL = 0x20000D50    # unsigned int  OutdoorVfdForceFullCount
A_II_PENDCNT = 0x20000D54  # unsigned int  OutdoorTypeIIPendingCount
A_II_LOWOFFCNT = 0x20000D58  # unsigned int  OutdoorTypeIILowOffCount
A_OUTPUT = 0x200000D4      # 输出口 output[0..7] = Y00..Y07

# ---- 宏 -> Parameter 下标 ----
IDX = {
    "UnitType": 165,          # OutdoorUnitTypeSet 机型
    "FanType": 166,           # OutdoorFanTypeSet 风机类型
    "TL": 172,                # CondFanTLSet
    "TLD": 173,               # CondFanTLDSet
    "MaxFreq": 176,           # FanMaxFreqSet 整数 Hz
    "MinFreq": 177,           # FanMinFreqSet 整数 Hz
    "Step": 178,              # FanStepSpeedSet（×10，0.1Hz/s）
    "MinRun": 179,
    "MinStop": 180,
    "Hold": 181,
    "FanOpenSet": 872,
    "FanOpenSet2": 874,
    "EnviTemp": 1420 + 2,     # EnviTempAI0Disp
    "FinTemp1": 1420 + 11,    # FinTemp1AI5Disp
    "FinTemp2": 1420 + 12,    # FinTemp2AI7Disp
}

LINES: list[str] = []


def line(s: str = "") -> None:
    LINES.append(s)


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    every = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0

    from pyocd.core.helpers import ConnectHelper

    # ⚠ connect_mode 必须是 attach —— pyocd 默认 halt 会把板子冻死。
    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        line("!! 没找到 ST-Link")
        _write()
        return 1
    session.open()
    tgt = session.target
    if tgt.get_state() == tgt.State.HALTED:
        line("!! 进入时 HALTED —— 已 resume")
        tgt.resume()

    def r8(a):
        return tgt.read_memory_block8(a, 1)[0]

    def r16s(i):
        v = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        x = v[0] | (v[1] << 8)
        return x - 0x10000 if x & 0x8000 else x

    def r32(a):
        v = tgt.read_memory_block8(a, 4)
        return v[0] | (v[1] << 8) | (v[2] << 16) | (v[3] << 24)

    p = {k: r16s(v) for k, v in IDX.items()}
    fan_type = p["FanType"]
    line(f"已连接 state={tgt.get_state().name}")
    line(f"机型={p['UnitType']}  风机类型={fan_type}"
         f"  ({['单风机双速','双风机两定','单风机变频','定速+双速','变频+定速'][fan_type] if 0 <= fan_type <= 4 else '?'})")
    line(f"TL={p['TL'] / 10.0:.1f}C  TLD={p['TLD'] / 10.0:.1f}C  TL+TLD={(p['TL'] + p['TLD']) / 10.0:.1f}C"
         f"  TL+TLD/2={(p['TL'] + p['TLD'] // 2) / 10.0:.1f}C")
    line(f"变频最高频={p['MaxFreq']} Hz  最低频={p['MinFreq']} Hz  加减载={p['Step'] / 10.0:.1f} Hz/s")
    line(f"最短运行={p['MinRun']}s  最短停止={p['MinStop']}s  冷凝保持={p['Hold']}s")
    line()

    line("=== 采样 ===")
    line("  t(s) | 环温 翅片M|m | Fan1 Fan2 Stg IIStg PendS PndCnt IIHi Dead LowOff |"
         " VfdOn FixOn VfdHz Load Unld Full | ChgSec | Y02 Y03 Y07")
    t0 = time.time()
    next_tl = 0.0
    next_wd = 0.0
    next_flush = 0.0
    prev_key = None
    while time.time() - t0 < seconds:
        el = time.time() - t0
        if el >= next_wd:
            next_wd = el + 10.0
            if tgt.get_state() == tgt.State.HALTED:
                line(f"  [{el:5.1f}] !! HALTED —— resume")
                tgt.resume()
        env = r16s(IDX["EnviTemp"])
        f1, f2 = r16s(IDX["FinTemp1"]), r16s(IDX["FinTemp2"])
        out = [r8(A_OUTPUT + i) for i in range(8)]
        cur = (r16s(IDX["FanOpenSet"]), r16s(IDX["FanOpenSet2"]), r8(A_STAGE),
               r8(A_II_STAGE), r8(A_II_PEND), r32(A_II_PENDCNT), r8(A_II_HIGH),
               r8(A_II_DEAD), r8(A_II_LOWOFF),
               r8(A_VFD_ON), r8(A_FIXED_ON), r32(A_VFD_SPEED),
               r32(A_VFD_LOAD), r32(A_VFD_UNLOAD), r32(A_VFD_FULL),
               r32(A_CHGSEC), out[2], out[3], out[7])
        # 变化判据只看状态字段：ChgSec 之类单调递增的计数器每秒都在变，
        # 带上它们会让每一行都被判成"有变化"，日志没法看。
        state_key = cur[:15] + cur[16:]
        if el >= next_tl or state_key != prev_key:
            c = cur
            line("  ".join((
                "%5.0f" % el,
                "%5.1f" % (env / 10.0),
                "%5.1f|%5.1f" % (max(f1, f2) / 10.0, min(f1, f2) / 10.0),
                "%4d" % c[0], "%4d" % c[1], "%3d" % c[2],
                "%5d" % c[3], "%5d" % c[4], "%6d" % c[5], "%4d" % c[6],
                "%4d" % c[7], "%6d" % c[8],
                "%5d" % c[9], "%5d" % c[10], "%5.1f" % (c[11] / 10.0),
                "%4d" % c[12], "%4d" % c[13], "%4d" % c[14],
                "%6d" % c[15],
                "%3d" % c[16], "%3d" % c[17], "%3d" % c[18],
            )))
            next_tl = el + every
        prev_key = state_key
        if el >= next_flush:
            next_flush = el + 5.0
            _write()
        time.sleep(0.2)

    if tgt.get_state() == tgt.State.HALTED:
        line("!! 结束 HALTED —— resume")
        tgt.resume()
    line(f"结束 state={tgt.get_state().name}")
    session.close()
    _write()
    return 0


def _write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_316_cooling_fan.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
