"""盯「定时化霜到底能不能触发」—— 拔传感器端子时跑这个。

要证/证伪的推断链：
    非环温传感器故障 -> TimerDefrostMode[0] 应变成 1        （钥匙）
    同一条件        -> SystemFault[0] -> 停系统 -> Y05 断     （扳机）
    停机后          -> CompRunTime[0] 归零、DefGapCount 停止累计
    DefEnable 启动还要求 ActualRun[i] && CompRunTime[i] >= 5 分钟
      => 若推断成立：TimerDefrostMode 变 1，但 Y05 立刻断、CompRunTime 归零、化霜永不启动

关键三列： **TMode**(定时模式) / **Y05**(压机输出) / **CRT**(压机连续运行秒)
     只要看到 TMode 1 的同时 Y05=0 且 CRT=0，死锁即坐实。

只读，attach 模式（绝不停核）。
跑法： python.exe tools/probe_316_timeddef.py 1800
"""

from __future__ import annotations

import pathlib
import sys
import time

PARAM_BASE = 0x2000164A

A_DEF_STATE = 0x20000DF0         # PSC316DefrostState
A_DEF_TIMED = 0x20000DF1         # PSC316DefrostTimedMode
A_DEF_ELIG = 0x20000DF6          # PSC316DefrostEligible[2]
A_DEF_ENDED = 0x20000DF8
A_DEF_STARTED = 0x20000DFA
A_NORMALENV = 0x20000E08         # NormalEnvLowCount
A_TIMEDENV = 0x20000E0C          # TimedEnvLowCount
A_DEF_RUNTIME = 0x20000E10
A_INDEFROST = 0x20000DB0
A_COMP = 0x20000DD4              # Comp[2]
A_FOUR = 0x20000DD9
A_FAN = 0x20000DDE
A_OUTPUT = 0x200000D4            # output[8] = Y00..Y07  -> Y05 = [5]
A_DEFGAP = 0x200026A0            # DefGapCount[5]
A_DEFCOMP0 = 0x200026D4          # DefComp0[5]
A_TIMERMODE = 0x200026FC         # TimerDefrostMode[5]
A_FINLOW = 0x2000274C            # FinLowCount[5]
A_COMPRUNTIME = 0x20003078       # CompRunTime[5]

COMPERR = 605
P_ENVI = 1422
P_FIN1 = 1431
P_ENABLE1 = 152                  # Comp1Enable (0=使能中 1=禁用)

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_316_timeddef.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 1800.0

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"})
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

    def r16m(a):
        b = tgt.read_memory_block8(a, 2)
        return b[0] | (b[1] << 8)

    def r16(i):
        b = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        v = b[0] | (b[1] << 8)
        return v - 0x10000 if v & 0x8000 else v

    def r32(a):
        b = tgt.read_memory_block8(a, 4)
        return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)

    def u32n(a, n):
        return [r32(a + 4 * i) for i in range(n)]

    say("=== 定时化霜可达性探针（拔探头时盯）===")
    say("版本 = %s   机型=%d 风机=%d   Comp1Enable[152]=%d"
        % ([r16(1000 + i) for i in range(6)], r16(165), r16(166), r16(P_ENABLE1)))
    say("环温 = %.1fC   翅片1 = %.1fC" % (r16(P_ENVI) / 10.0, r16(P_FIN1) / 10.0))
    say("化霜参数: [182]定时化霜温度设定=%.1f  [183]定时间隔=%d分  [184]定时化霜时间=%d分"
        "  [185]压机最小运行=%d分"
        % (r16(182) / 10.0, r16(183), r16(184), r16(185)))
    say()
    say("  ⚠ Comp1Y05 列 = output[0] (=Y00)，宏名里的 Y05 是旧引脚号")
    say("  故障字(605~620)  TMode Y00 CRT Gap0 DefC0 | St Elig End Strt Comp Four Fan |"
        " NEnv TEnv FinLow0 | 环温 翅片1 | 动作")
    prev = None
    prev_fault = None
    t0 = time.time()
    nxt_wd = 0.0
    while time.time() - t0 < seconds:
        el = time.time() - t0
        if el >= nxt_wd:
            nxt_wd = el + 10.0
            if tgt.get_state() == tgt.State.HALTED:
                say(f"  [{el:6.1f}] !! HALTED —— resume")
                tgt.resume()
        try:
            faults = [r16m(PARAM_BASE + (COMPERR + k) * 2) for k in range(0, 16)]
            tmode = r32(A_TIMERMODE)              # TimerDefrostMode[0]
            # ⚠ Comp1Y05 宏名骗人：User.h:249 是 #define Comp1Y05 Y00 -> output[0]
            #   （同 Fan1Y03->Y02 的旧引脚号遗留）。以前读 output[5] 是错的。
            y05 = r8n(A_OUTPUT, 8)[0]
            crt = u32n(A_COMPRUNTIME, 1)[0]
            gap = u32n(A_DEFGAP, 1)[0]
            st = r8(A_DEF_STATE)
            elig = r8n(A_DEF_ELIG, 2)
            ended = r8n(A_DEF_ENDED, 2)
            strt = r8n(A_DEF_STARTED, 2)
            comp = r8n(A_COMP, 2)
            four = r8n(A_FOUR, 2)
            fan = r8n(A_FAN, 2)
            nenv = r32(A_NORMALENV)
            tenv = r32(A_TIMEDENV)
            finlow = u32n(A_FINLOW, 1)[0]
            dcomp0 = u32n(A_DEFCOMP0, 1)[0]
            dstate_timed = r8(A_DEF_TIMED)
            env = r16(P_ENVI)
            fin1 = r16(P_FIN1)
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:6.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue

        act = ""
        if prev_fault is not None and faults != prev_fault:
            ch = ["%d:%d->%d" % (COMPERR + k, prev_fault[k], faults[k])
                  for k in range(16) if faults[k] != prev_fault[k]]
            act = "故障字变化 " + ",".join(ch)
            say(f"  [{el:6.1f}] >>> {act}")
            act = ""
        prev_fault = faults

        key = (tuple(faults), tmode, y05, crt, gap, st, tuple(elig), tuple(ended),
               tuple(strt), tuple(comp), tuple(four), tuple(fan), nenv, tenv,
               finlow, dcomp0, dstate_timed, env, fin1)
        if key != prev:
            nz = ",".join("%d=%d" % (COMPERR + k, faults[k])
                          for k in range(16) if faults[k])
            say("  %6.0f  %-16s  %4d %3d %5d %5d | %2d %s %s %s %s %s %s |"
                " %4d %4d %6d | %5.1f %5.1f |"
                % (el, nz if nz else "-", tmode, y05, crt, gap, st, elig, ended,
                   strt, comp, four, fan, nenv, tenv, finlow,
                   env / 10.0, fin1 / 10.0))
            prev = key
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
