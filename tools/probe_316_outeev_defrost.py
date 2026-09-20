"""盯 316（外机1）：**室外机 EEV** 在化霜时是否关闭 + 手动化霜链路。

验两条：
  #2 规格书 3.9「化霜运行时：**室外机**电子膨胀阀处于关闭状态」
     制热时室外 EEV 是按过热度控制的（有开度），化霜一开始必须归 0。
  #5 手动化霜（HMI -> HandDef -> UART5 -> 316 Parameter[1410]）
     持久痕迹：DefComp0[0]=2（手动化霜态）、CanDefrost[0]=5

316 侧 EEV 参数（User.h:751/757）：
    NewAddValue = 805  -> EEV1..4 目标步数
    OldAddValue = 809  -> EEV1..4 当前步数
    EEV1OldAddValueDisp = PLCREADPara+19 = 1419  （上报 330 的显示值）

只读，attach 模式（绝不停核）。
跑法： python.exe tools/probe_316_outeev_defrost.py 1800
"""

from __future__ import annotations

import pathlib
import sys
import time

PARAM_BASE = 0x2000164A

A_DEF_STATE = 0x20000DF0         # PSC316DefrostState
A_DEF_TIMED = 0x20000DF1         # PSC316DefrostTimedMode
A_DEF_ENDED = 0x20000DF8
A_DEF_RUNTIME = 0x20000E10       # PSC316DefrostRunTime[2]
A_INDEFROST = 0x20000DB0
A_COMP = 0x20000DD4
A_FOUR = 0x20000DD9
A_FAN = 0x20000DDE
A_DEFCOMP0 = 0x200026D4          # DefComp0[5]
A_DEFGAP = 0x200026A0            # DefGapCount[5]
A_BOARDADDR = 0x2000011E         # BoardAddressSet
A_UNITREAD = 0x200030DC          # UnitReadStatus[]，18 × 508
A_UNITWRITE = 0x20005494         # UnitWriteStatus[]，18 × 220
READ_STEP = 508
WRITE_STEP = 220
OFF_CANDEFROST = 304
OFF_DEFSIGNAL = 16

NEW = 805                        # EEV1..4 目标
OLD = 809                        # EEV1..4 当前
RUNFLAG = 813                    # EEV1..4 运行指示
P_EEVCTRLNUM = 804               # 本机实际控制几路 EEV（未用的通道 OldAddValue 是残留值）
P_ENVI = 1422
P_FIN1 = 1431
P_DEFROSTFLAG = 1410             # Comp1DefrostFlag（UART5 脉冲）
P_ALLOWREAD = 1420               # PLCREADPara: [1420]=回给330的化霜请求

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_316_outeev_defrost.txt").write_text(
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

    board = r8(A_BOARDADDR)
    say("=== 316 室外 EEV + 化霜（外机1）===")
    say("版本 = %s   机型=%d 风机=%d   BoardAddressSet=%d"
        % ([r16(1000 + i) for i in range(6)], r16(165), r16(166), board))
    say("环温 = %.1fC   翅片1 = %.1fC" % (r16(P_ENVI) / 10.0, r16(P_FIN1) / 10.0))
    say("**EEVCtrlNum[804] = %d**  <- 本机实际控制几路电磁头；第 %d 路之后是未用通道"
        % (r16(P_EEVCTRLNUM), r16(P_EEVCTRLNUM)))
    say()
    say("  ⚠ 室外 EEV 在制热时**应该是有开度的**（按过热度控制）；")
    say("     化霜一开始必须归 0 —— 那就是 #2 的判据。")
    say()
    say("   t | St Tmd | Comp Four Fan | DefC0 | EEV1..4 目标/当前/跑 | CanDef DSig |"
        " f1410 Gap0 DefRT | 环温 翅片1 | 动作")
    prev = None
    prev_flag = 0
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
            st = r8(A_DEF_STATE)
            tmd = r8(A_DEF_TIMED)
            ended = r8n(A_DEF_ENDED, 2)
            comp = r8n(A_COMP, 2)
            four = r8n(A_FOUR, 2)
            fan = r8n(A_FAN, 2)
            dcomp0 = u32n(A_DEFCOMP0, 1)[0]
            gap0 = u32n(A_DEFGAP, 1)[0]
            new = [r16(NEW + i) for i in range(4)]
            old = [r16(OLD + i) for i in range(4)]
            rflg = [r16(RUNFLAG + i) for i in range(4)]
            can = [r16m(A_UNITREAD + board * READ_STEP + OFF_CANDEFROST + 2 * i)
                   for i in range(2)]
            dsig = [r16m(A_UNITWRITE + board * WRITE_STEP + OFF_DEFSIGNAL + 2 * i)
                    for i in range(2)]
            flag = r16(P_DEFROSTFLAG)
            allow = r16(P_ALLOWREAD)
            env = r16(P_ENVI)
            fin1 = r16(P_FIN1)
            rt = u32n(A_DEF_RUNTIME, 2)
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:6.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue

        if flag and not prev_flag:
            say(f"  [{el:6.1f}] >>> Parameter[1410] Comp1DefrostFlag = {flag} "
                f"（UART5 脉冲到了！1=开始 2=结束）")
        prev_flag = flag

        key = (st, tmd, tuple(ended), tuple(comp), tuple(four), tuple(fan), dcomp0,
               gap0, tuple(new), tuple(old), tuple(rflg), tuple(can), tuple(dsig),
               flag, allow, env, fin1, tuple(rt))
        if key != prev:
            eev = " ".join("%d/%d/%d" % (new[i], old[i], rflg[i]) for i in range(4))
            say("  %5.0f | %2d %3d | %s %s %s | %5d | %-29s | %s %s | %4d %4d %5d |"
                " %5.1f %5.1f |"
                % (el, st, tmd, comp, four, fan, dcomp0, eev, can, dsig,
                   flag, gap0, rt[0], env / 10.0, fin1 / 10.0))
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
