"""盯 316 的**化霜**状态机（V12.14 符号表核对过的地址）。

**2026-09-17 第二版**：第一版漏了几列，导致规格书 4.4 有几条判据没验到。本版补齐：

  规格书 4.4 item1 化霜开始 7 条件 -> 探针里对应的列
    ① 热泵制热 + 至少一台压机在转   -> WMd(工作模式) + Comp
    ② 环温<10 保持 60 秒以上        -> NEnv (NormalEnvLowCount) / TEnv
    ③ 压机运转 >=【化霜开始前压缩运转最小时间】 -> **CRT (CompRunTime)**  ← 一版漏了
    ④ 翅片<【…】保持 30 秒以上      -> FinLow0/1 + 翅片列
    ⑤ 温差 >【…】                   -> 环温 − 翅片（两列都在，可算）
    ⑥ 间隔 >【…】                   -> Gap0/Gap1（分钟）+ GapNeed
    ⑦ 没有其它室外机在化霜          -> **Permit(330 授权) + SysHaveDef + CanDef**  ← 一版漏了
  item3 化霜开始动作
    向室内机发化霜开始/结束指令      -> **Sig0/Sig1 (UnitWriteStatus.DefrostSignal)** ← 一版漏了
    屏蔽低压开关                     -> （间接：InDefrost 期间 LowPressCount 被清）
    室外机风机关                     -> **Fan** ← 一版漏了
    四通阀失电                       -> **Four** ← 一版漏了
    所有压机开（已开的不关，未开的间隔30秒开）-> Comp + Strt
  item2 化霜结束三原因（满足其一）
    翅片达【…】/ 高压开关跳开 / 到时 -> FinTemp 列 / （X 输入，台面测不到）/ RunTime vs MaxDef
  item4 结束动作
    所有压缩机关闭 + 延时60秒        -> Comp + St (状态2) + StateT
    向室内机发化霜结束指令            -> Sig0/Sig1 + CanDef(7)

只读，attach 模式（绝不停核）。

跑法：
    python.exe tools/probe_316_defrost.py --status
    python.exe tools/probe_316_defrost.py 1800
    python.exe tools/probe_316_defrost.py 1800 5
"""

from __future__ import annotations

import pathlib
import sys
import time

PARAM_BASE = 0x2000164A          # int16_t Parameter[]

# ---- .axf 符号表核对过的绝对地址（V12.14）----
A_DEF_STATE = 0x20000DF0         # unsigned char PSC316DefrostState
A_DEF_TIMED = 0x20000DF1         # unsigned char PSC316DefrostTimedMode
A_ENVHIGHBAND = 0x20000DF2       # unsigned char EnvHighBand（V12.14 新增）
A_DEF_ELIG = 0x20000DF6          # unsigned char[2] PSC316DefrostEligible
A_DEF_ENDED = 0x20000DF8         # unsigned char[2] PSC316DefrostEnded
A_DEF_STARTED = 0x20000DFA       # unsigned char[2] PSC316DefrostStarted
A_DEF_STATETIME = 0x20000E00     # unsigned int  PSC316DefrostStateTime
A_DEF_FIRSTAT = 0x20000E04       # unsigned int  PSC316DefrostFirstStartAt
A_NORMALENV = 0x20000E08         # unsigned int  NormalEnvLowCount
A_TIMEDENV = 0x20000E0C          # unsigned int  TimedEnvLowCount
A_DEF_RUNTIME = 0x20000E10       # unsigned int[2] PSC316DefrostRunTime（化霜已走秒）
A_INDEFROST = 0x20000DB0         # unsigned char InDefrost
A_COMP = 0x20000DD4              # unsigned char[2] Comp
A_FOUR = 0x20000DD9              # unsigned char[2] Four（化霜要求失电）
A_FAN = 0x20000DDE               # unsigned char[2] Fan（化霜要求关）
A_OUTPUT = 0x200000D4            # unsigned char[8] output[] = Y00..Y07
A_SYSHAVEDEF = 0x20002664        # unsigned int[5] SysHaveDef
A_DEFGAP = 0x200026A0            # unsigned int[5] DefGapCount（压机累计运行秒）
A_DEFCOMP0 = 0x200026D4          # unsigned int[5] DefComp0
A_TIMERMODE = 0x200026FC         # unsigned int[5] TimerDefrostMode
A_FINLOW = 0x2000274C            # unsigned int[5] FinLowCount
A_COMPRUNTIME = 0x20003078       # unsigned int[5] CompRunTime（压机连续运行秒，一停就归零）
A_COMPSTOPTIME = 0x2000308C      # unsigned int[5] CompStopTime
A_BOARDADDR = 0x2000011E         # unsigned char BoardAddressSet
A_UNITREAD = 0x200030DC          # UnitReadStatus[]，18 × 508（9144）
A_UNITWRITE = 0x20005494         # UnitWriteStatus[]，18 × 220（3960）
READ_STEP = 508
WRITE_STEP = 220
OFF_CANDEFROST = 304             # UnitReadStatus[].CanDefrost[4]
OFF_DEFSIGNAL = 16               # UnitWriteStatus[].DefrostSignal[4]

# ---- Parameter 下标 ----
P_USERWORKMODE = 1
P_UNITTYPE = 165
P_FANTYPE = 166
P_ENVI = 1420 + 2                # EnviTempAI0Disp
P_FIN1 = 1420 + 11               # FinTemp1
P_FIN2 = 1420 + 12               # FinTemp2
P_DEFROSTPERMIT = 1400 + 9       # DefrostPermit（330 授权）
P_DEFROSTASK1 = 1420 + 0         # DefrostAsk1（化霜请求信号 -> 室内机）
P_DEFROSTASK2 = 1420 + 1
P_C1DEFFLAG = 1400 + 10
P_C2DEFFLAG = 1400 + 11
P_OUTDOOR_SPEC = 165
DEFROST_PARAMS = [
    (17, "环境温度定时化霜温度设定值", 10),
    (18, "环境温度定时化霜时间间隔", 1),
    (19, "环境温度定时化霜时间", 1),
    (20, "化霜开始前压缩运转最小时间", 1),
    (21, "化霜开始前翅片温度", 10),
    (22, "环境温度与翅片温度差", 10),
    (23, "环温>0 两次化霜间隔", 1),
    (24, "环温<0 两次化霜间隔", 1),
    (25, "化霜结束室外机翅片温度", 10),
    (26, "环温>0 化霜时间", 1),
    (27, "环温<0 化霜时间", 1),
]

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_316_defrost.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    status_only = "--status" in sys.argv
    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 600.0
    every = float(nums[1]) if len(nums) > 1 else 10.0

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

    ba = r8(A_BOARDADDR)
    rb = A_UNITREAD + ba * READ_STEP
    wb = A_UNITWRITE + ba * WRITE_STEP

    ver = [r16(1000 + i) for i in range(6)]
    say("=== 316 化霜探针 v2 ===")
    say(f"版本={ver}  机型={r16(P_UNITTYPE)}  风机类型={r16(P_FANTYPE)}"
        f"  BoardAddressSet={ba} (槽位)")
    if ver[2] != 14:
        say(f"!! 不是 V12.14（minor={ver[2]}）—— 地址是按 V12.14 符号表取的")
    say()
    say("--- 化霜参数（网关 17~27）---")
    for off, nm, sc in DEFROST_PARAMS:
        say("  [%2d] %-28s = %7.1f" % (off, nm, r16(P_OUTDOOR_SPEC + off) / sc))
    say(f"  EnvHighBand = {r8(A_ENVHIGHBAND)}  (0=满时间 1=-1分钟)")
    say()
    say("--- 当前态 ---")
    say(f"  工作模式={r16(P_USERWORKMODE)}  InDefrost={r8(A_INDEFROST)}"
        f"  DefrostState={r8(A_DEF_STATE)}  TimedMode={r8(A_DEF_TIMED)}")
    say(f"  环温={r16(P_ENVI) / 10.0:.1f}C  翅片1={r16(P_FIN1) / 10.0:.1f}C"
        f"  翅片2={r16(P_FIN2) / 10.0:.1f}C")
    say(f"  Comp={r8n(A_COMP, 2)}  Fan={r8n(A_FAN, 2)}  Four={r8n(A_FOUR, 2)}")
    say(f"  DefrostPermit={r16(P_DEFROSTPERMIT)}  Ask1/2={r16(P_DEFROSTASK1)}/{r16(P_DEFROSTASK2)}"
        f"  CI/2DefFlag={r16(P_C1DEFFLAG)}/{r16(P_C2DEFFLAG)}")
    say(f"  CanDefrost={[r32(rb + OFF_CANDEFROST + 4 * i) for i in range(2)]}"
        f"  DefrostSignal={[r32(wb + OFF_DEFSIGNAL + 4 * i) for i in range(2)]}")
    say(f"  DefGapCount={[r32(A_DEFGAP + 4 * i) for i in range(2)]}"
        f"  CompRunTime={[r32(A_COMPRUNTIME + 4 * i) for i in range(2)]}")
    say(f"  SysHaveDef={[r32(A_SYSHAVEDEF + 4 * i) for i in range(2)]}"
        f"  DefComp0={[r32(A_DEFCOMP0 + 4 * i) for i in range(2)]}")
    say(f"  TimerMode={[r32(A_TIMERMODE + 4 * i) for i in range(2)]}"
        f"  FinLow={[r32(A_FINLOW + 4 * i) for i in range(2)]}")
    say(f"  EnvLow: Normal={r32(A_NORMALENV)} Timed={r32(A_TIMEDENV)}")

    if status_only:
        if tgt.get_state() == tgt.State.HALTED:
            say("!! 结束 HALTED —— resume")
            tgt.resume()
        session.close()
        write()
        return 0

    say()
    say("=== 10Hz 采样（只记变化）===")
    say("  t | WMd 环温 翅片1|2 | St Tmd InD | Elig End Strt | DefRT StateT | Comp |"
        " Gap0 Gap1 | CRT0 CRT1 | FinLow0/1 | NEnv TEnv | DefComp0/1 | RedBnd |"
        " Perm Ask | CanDef | Sig | Fan Four | Y02 Y03 Y07")
    prev = None
    t0 = time.time()
    nxt_wd = 0.0
    nxt_force = 0.0
    while time.time() - t0 < seconds:
        el = time.time() - t0
        if el >= nxt_wd:
            nxt_wd = el + 10.0
            if tgt.get_state() == tgt.State.HALTED:
                say(f"  [{el:6.1f}] !! HALTED —— resume")
                tgt.resume()
        force = el >= nxt_force
        if force:
            nxt_force = el + every
        try:
            cur = (
                r16(P_USERWORKMODE),
                r8(A_DEF_STATE), r8(A_DEF_TIMED), r8(A_INDEFROST),
                tuple(r8n(A_DEF_ELIG, 2)), tuple(r8n(A_DEF_ENDED, 2)),
                tuple(r8n(A_DEF_STARTED, 2)), tuple(r8n(A_COMP, 2)),
                tuple(r8n(A_FAN, 2)), tuple(r8n(A_FOUR, 2)),
                r16(P_DEFROSTPERMIT), r16(P_DEFROSTASK1), r16(P_DEFROSTASK2),
                tuple(r32(rb + OFF_CANDEFROST + 4 * i) for i in range(2)),
                tuple(r32(wb + OFF_DEFSIGNAL + 4 * i) for i in range(2)),
                tuple(r32(A_SYSHAVEDEF + 4 * i) for i in range(2)),
                tuple(r32(A_DEFCOMP0 + 4 * i) for i in range(2)),
                tuple(min(r32(A_DEFGAP + 4 * i), 20000) // 60 for i in range(2)),
                tuple(min(r32(A_COMPRUNTIME + 4 * i), 20000) // 60 for i in range(2)),
                tuple(min(r32(A_FINLOW + 4 * i), 60) for i in range(2)),
                min(r32(A_NORMALENV), 60), min(r32(A_TIMEDENV), 60),
                r8(A_ENVHIGHBAND),
            )
            rt = [r32(A_DEF_RUNTIME + 4 * i) for i in range(2)]
            st = r32(A_DEF_STATETIME)
            outc = r8n(A_OUTPUT, 8)
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:6.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue
        if cur != prev or force:
            say("  ".join((
                "%6.0f" % el,
                "%3d" % cur[0],
                "%5.1f" % (r16(P_ENVI) / 10.0),
                "%5.1f|%4.1f" % (r16(P_FIN1) / 10.0, r16(P_FIN2) / 10.0),
                "%2d" % cur[1], "%3d" % cur[2], "%3d" % cur[3],
                "%s" % (cur[4],), "%s" % (cur[5],), "%s" % (cur[6],),
                "%s" % (rt,), "%5d" % st,
                "%s" % (cur[7],),
                "%3d %3d" % cur[17],          # Gap0 Gap1（分钟）
                "%3d %3d" % cur[18],          # CRT0 CRT1（压机连续运行，分钟）<- item1-3
                "%3d/%3d" % cur[19],          # FinLow0/1
                "%4d %4d" % (cur[20], cur[21]),   # NEnv TEnv
                "%s" % (cur[16],),            # DefComp0/1
                "%d" % cur[22],               # EnvHighBand
                "%4d %3d" % (cur[10], cur[11]),   # Permit Ask1
                "%s" % (cur[13],),            # CanDefrost
                "%s" % (cur[14],),            # DefrostSignal（化霜开始/结束指令）
                "%s %s" % (cur[8], cur[9]),   # Fan Four
                "%d  %d   %d" % (outc[2], outc[3], outc[7]),   # Y02 Y03 Y07
            )))
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
