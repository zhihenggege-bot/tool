"""10Hz 盯住 316 的风机换挡状态机，看 OutdoorFanChangeSeconds 到底被谁清零。

只读，attach 模式（绝不停核）。跑法：
    python.exe tools/probe_316_fan_tick.py [秒数]
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PARAM_BASE = 0x2000164A

# .axf 符号表核对过的绝对地址
A_STAGE = 0x20000D00          # unsigned char OutdoorFanStage
A_TWO_FAN = 0x20000D04        # unsigned char OutdoorHeatTwoFan
A_II_HIGH = 0x20000D06        # unsigned char OutdoorTypeIIFan2High
A_II_DEAD = 0x20000D07        # unsigned char OutdoorTypeIIFan2SwapDead
A_LASTPHYS = 0x20000D1C       # unsigned char OutdoorFanLastPhysical[2]
A_CHGSEC = 0x20000D28         # unsigned int  OutdoorFanChangeSeconds
A_NOCOMPSEC = 0x20000D2C      # unsigned int  OutdoorFanNoCompSeconds
A_RUN = 0x20000DA0            # unsigned int  OutdoorFanRunSeconds[2]
A_STOP = 0x20000DA8           # unsigned int  OutdoorFanStopSeconds[2]
A_CMD = 0x2000005C            # unsigned int  OutdoorFanCommandRunSeconds[2]

IDX_FAN1 = 872                # FanOpenSet
IDX_FAN2 = 874                # FanOpenSet2
IDX_TYPE = 165 + 1            # OutdoorFanTypeSet

LINES: list[str] = []


def line(s: str = "") -> None:
    LINES.append(s)


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0

    from pyocd.core.helpers import ConnectHelper

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
    line(f"已连接 state={tgt.get_state().name}")

    def r8(a):
        return tgt.read_memory_block8(a, 1)[0]

    def r16s(a):
        v = tgt.read_memory_block8(a, 2)
        x = v[0] | (v[1] << 8)
        return x - 0x10000 if x & 0x8000 else x

    def r32(a):
        v = tgt.read_memory_block8(a, 4)
        return v[0] | (v[1] << 8) | (v[2] << 16) | (v[3] << 24)

    def snap():
        return (
            r16s(PARAM_BASE + IDX_FAN1 * 2),
            r16s(PARAM_BASE + IDX_FAN2 * 2),
            r8(A_STAGE),
            r8(A_II_HIGH),
            r8(A_II_DEAD),
            r8(A_TWO_FAN),
            r8(A_LASTPHYS), r8(A_LASTPHYS + 1),
            r32(A_CHGSEC),
            r32(A_CMD), r32(A_CMD + 4),
            r32(A_RUN), r32(A_RUN + 4),
            r32(A_STOP), r32(A_STOP + 4),
        )

    hdr = ("Fan1 Fan2 Stg IIHi Dead TwoF LastPh  ChgSec    Cmd0   Cmd1   Run0  Run1   Stop0  Stop1")
    line()
    line("=== 10Hz 采样（外机1）===")
    line("  t(s)  " + hdr)
    t0 = time.time()
    next_wd = 0.0
    next_flush = 0.0
    prev = None
    n = 0
    while time.time() - t0 < seconds:
        el = time.time() - t0
        if el >= next_wd:
            next_wd = el + 10.0
            if tgt.get_state() == tgt.State.HALTED:
                line(f"  [{el:5.1f}] !! HALTED —— resume")
                tgt.resume()
        cur = snap()
        if cur != prev:
            v = (el,) + cur
            line("  " + " ".join((
                "%5.2f" % v[0],
                "%4d" % v[1], "%4d" % v[2], "%3d" % v[3],
                "%4d" % v[4], "%4d" % v[5], "%4d" % v[6],
                "%2d,%2d" % (v[7], v[8]),
                "%6d" % v[9], "%6d" % v[10], "%6d" % v[11],
                "%6d" % v[12], "%6d" % v[13], "%6d" % v[14],
                "%6d" % v[15],
            )))
            n += 1
        prev = cur
        # 边跑边落盘，中途就能读进度（不然要等整轮跑完）
        if el >= next_flush:
            next_flush = el + 5.0
            _write()
        time.sleep(0.1)

    line()
    line(f"共 {n} 次状态变化 / {seconds:.0f} 秒")
    if tgt.get_state() == tgt.State.HALTED:
        line("!! 结束 HALTED —— resume")
        tgt.resume()
    line(f"结束 state={tgt.get_state().name}")
    session.close()
    _write()
    return 0


def _write() -> None:
    p = pathlib.Path(__file__).resolve().parent / "probe_316_fan_tick.txt"
    p.write_text("\n".join(LINES) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
