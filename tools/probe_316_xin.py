"""盯 316 的 X 输入口 + 高压开关判据（验「高压开关跳开」用）。

背景：
    X00 = input[0]                                  (io.h:26)
    X_00 = InPutStatusSet0 ? X00 : !X00             (user.c:451，极性可选)
    Comp1HightOverX06 = X_00   Comp2HightOverX10 = X_02      (User.h:238/240)
    input[] @0x200000dc (8 字节)   X_00/X_01/X_02.. @0x20000120 (1 字节一个)

化霜结束判据里的那条（DefAction.c）：
    if(... || (Comp1HightOverX06==1) || ...) { Ended[0]=1; Comp[0]=0; }
以及报警那条（ErrorCheck.c:355）：
    if(InDefrost) { HighPressCount[]=0; }        // 化霜中不报警
    else { if(Comp1HightOverX06==1) Comp1HightPressErr=1; }

所以本探针同时采：X 输入、X_00/X_02、化霜状态机、Comp1/2HightPressErr。

跑法：
    python.exe tools/probe_316_xin.py 120        # 盯 120 秒
"""

from __future__ import annotations

import pathlib
import sys
import time

PARAM_BASE = 0x2000164A
A_INPUT = 0x200000DC             # unsigned char input[8] = X00..X07
A_XVAL = 0x20000120              # unsigned char X_00, X_01, X_02, ... （1 字节一个）
A_DEF_STATE = 0x20000DF0
A_DEF_ENDED = 0x20000DF8
A_DEF_STARTED = 0x20000DFA
A_DEF_RUNTIME = 0x20000E10
A_INDEFROST = 0x20000DB0
A_COMP = 0x20000DD4
A_FOUR = 0x20000DD9
A_OUTPUT = 0x200000D4
A_DEFSTATETIME = 0x20000E00

P_C1HPERR = 606                  # Comp1HightPressErr = Parameter[COMPERR+1]
P_C2HPERR = 607                  # Comp2HightPressErr = Parameter[COMPERR+2]
# ⚠ 608/609 是 AI0TempErr/AI1TempErr（高压【传感器】故障字），不是开关报警。
#   规格书「高压开关跳开（此时高压不报警）」里的"报警" = CompXHightPressErr = 606/607。
P_ENVI = 1422
P_FIN1 = 1431
P_FIN2 = 1432
P_UNITTYPE = 165
P_FANTYPE = 166

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_316_xin.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    if nums:
        seconds = float(nums[0])

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        say("!! 没找到 ST-Link")
        write()
        return 1
    session.open()
    tgt = session.target
    if tgt.get_state() == tgt.State.HALTED:
        say("!! 进入时 HALTED —— 已 resume")
        tgt.resume()

    def r8(a):
        return tgt.read_memory_block8(a, 1)[0]

    def r8n(a, n):
        return list(tgt.read_memory_block8(a, n))

    def r16(i):
        b = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        v = b[0] | (b[1] << 8)
        return v - 0x10000 if v & 0x8000 else v

    def r32(a):
        b = tgt.read_memory_block8(a, 4)
        return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)

    say("=== 316 X 输入口 + 高压开关判据 ===")
    say(f"版本={[r16(1000 + i) for i in range(6)]}  机型={r16(P_UNITTYPE)}"
        f"  风机类型={r16(P_FANTYPE)}")
    say(f"环温={r16(P_ENVI) / 10.0:.1f}  翅片1={r16(P_FIN1) / 10.0:.1f}"
        f"  翅片2={r16(P_FIN2) / 10.0:.1f}")
    say()
    say("  t | input[0..7] | X_00..X_07 | Comp1/2HightOver | Err608/609 |"
        " St Ended Comp | RunTime")
    prev = None
    t0 = time.time()
    while time.time() - t0 < seconds:
        el = time.time() - t0
        if tgt.get_state() == tgt.State.HALTED:
            say(f"  [{el:6.1f}] !! HALTED —— resume")
            tgt.resume()
        try:
            inp = r8n(A_INPUT, 8)
            xv = r8n(A_XVAL, 8)
            cur = (tuple(inp), tuple(xv), r16(P_C1HPERR), r16(P_C2HPERR),
                   r8(A_DEF_STATE), tuple(r8n(A_DEF_ENDED, 2)), tuple(r8n(A_COMP, 2)))
            rt = [r32(A_DEF_RUNTIME + 4 * i) for i in range(2)]
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:6.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue
        if cur != prev:
            say("  %6.1f  %s  %s  X00=%d X02=%d  %d/%d  St=%d Ended=%s Comp=%s  RT=%s"
                % (el, inp, xv, xv[0], xv[2], cur[2], cur[3], cur[4], cur[5], cur[6], rt))
            prev = cur
        time.sleep(0.1)

    if tgt.get_state() == tgt.State.HALTED:
        say("!! 结束 HALTED —— resume")
        tgt.resume()
    say(f"结束 state={tgt.get_state().name}")
    session.close()
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
