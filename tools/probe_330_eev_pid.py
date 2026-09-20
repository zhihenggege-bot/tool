"""330 室内 EEV **动态记录**（制冷工况）：读固件内部的 E(K)/E(K-1)/E(K-2) 当场验算。

规格书 3.9：制冷运行时 **室内机** EEV 按吸气过热度控制，初始步数 = 【电子膨胀阀起始开度】。

与 316 版（`probe_316_eev_pid.py`）同一个内核，但：
  - 参数块不同：330 是 `[366..372]` + `[16]` + `[411]`（316 是 `[198..206]` + `[201]`）
  - EEV 步数是 8 路：`[1145..1152]` 目标 / `[1153..1160]` 当前
  - ⚠ **过热度不由 330 计算** —— 它来自 316 上报的 `UnitReadStatus[].BII[]`。
    所以本探针不显示原始温度，只显示固件内部的 E(K)（= 过热度 − Y），够验公式。

地址（fromelf -s 取自 `Project/Obj/PSC330RK-V10.axf`）：
    EEVSpecErrHist        0x200023f0  int32[8][3]  -> EEV i: E0=+i*12, E1=+i*12+4, E2=+i*12+8
    EEVSpecResidualMilli  0x20002470  int64[8]     -> EEV i: +i*8
    UnitReadStatus        0x200080C8  step=196, CompStatus 偏移 98

只读，attach 模式（绝不停核）。
跑法： python.exe tools/probe_330_eev_pid.py 900
"""

from __future__ import annotations

import pathlib
import sys
import time

TARGET = "stm32f407ze"
PARAM_BASE = 0x200030C8
A_ERRHIST = 0x200023F0
A_RESID = 0x20002470
A_UNITREAD = 0x200080C8
R_STEP = 196
R_COMPSTATUS = 98
# 关闭状态机（验「常规 +20 / 紧急 +10」用）
A_CLOSEMODE = 0x20000F2C        # uint8[8]  0=NONE 1=NORMAL 2=EMERGENCY
A_CLOSETGT = 0x200024B0         # int32[8]  关闭目标
# PID 周期诊断（查「步率只有一半」）
A_PIDCOUNT = 0x20002450         # int32[8]  周期计数
A_VALIDSMP = 0x20000F24         # uint8[8]  有效采样数（historyReady 用）

CLOSE_MODE = {0: "-", 1: "正常", 2: "紧急"}

# ---- 330 室内 EEV 参数 ----
P_WMODE = 1
P_TP = 16                  # EEVPidScanTimeSet
P_PIDEN = 365              # EEVSpecPidEnableSet
P_Y = 366                  # EEVSuperHeatTargetSet   0.1C
P_YD = 367                 # EEVSuperHeatDeadSet     0.1C
P_KP = 368
P_TI = 369
P_TD = 370
P_LIMIT = 371
P_DEFSTEP = 372            # 化霜开度
P_START = 411              # 起始开度
P_NEW, P_OLD = 1145, 1153
NEEV = 4

WM = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排风", 5: "自动"}
COMP = {0: "停", 1: "故障", 2: "制冷", 3: "制热", 4: "除霜", 5: "禁用"}

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_330_eev_pid.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


def tdiv(a: int, b: int) -> int:
    """C 的整数除法：向零截断（Python 的 // 是向下取整，负数会差 1）。"""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 900.0

    session = ConnectHelper.session_with_chosen_probe(
        target_override=TARGET, options={"frequency": 1000000, "connect_mode": "attach"})
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

    def r16m(a):
        b = tgt.read_memory_block8(a, 2)
        return b[0] | (b[1] << 8)

    def ps(i):
        v = r16m(PARAM_BASE + i * 2)
        return v - 0x10000 if v & 0x8000 else v

    def r32s(a):
        b = tgt.read_memory_block8(a, 4)
        v = b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
        return v - 0x100000000 if v & 0x80000000 else v

    def r64s(a):
        return (r32s(a + 4) << 32) | (r32s(a) & 0xFFFFFFFF)

    say("=== 330 室内 EEV 动态记录（规格书 3.9 验算）===")
    say("工作模式 = %s   机型[165]=%d 风机[166]=%d"
        % (WM.get(ps(P_WMODE), ps(P_WMODE)), ps(165), ps(166)))
    say("参数: Y=%.1fC  YD=%.1fC  KP=%d  TP=%ds  TI=%ds  TD=%ds  起始开度=%d  "
        "每周期最大=%d  化霜开度=%d  PID使能=%d"
        % (ps(P_Y) / 10.0, ps(P_YD) / 10.0, ps(P_KP), ps(P_TP), ps(P_TI), ps(P_TD),
           ps(P_START), ps(P_LIMIT), ps(P_DEFSTEP), ps(P_PIDEN)))
    say()
    say("  ⚠ 过热度由 316 上报，330 本地只有 E(K)=过热度−Y")
    say("  EEV1..4 显示 目标/当前；Δ 只在变化时打；累计开/关按 EEV1 统计")
    say()
    say("   t | WMd | 外机1 压机 | EEV1 E0 E1 E2 算式 分支后 | EEV1..4 目标/当前 | 关模式 关目标 |"
        " 周期 采样 | 累计开 累计关 | 备注")
    prev = None
    prev_new = None
    acc_o = acc_c = 0
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
            wm = ps(P_WMODE)
            cs = [r16m(A_UNITREAD + 1 * R_STEP + R_COMPSTATUS + 2 * i) for i in range(2)]
            new = [ps(P_NEW + i) for i in range(NEEV)]
            old = [ps(P_OLD + i) for i in range(NEEV)]
            e0 = r32s(A_ERRHIST + 0)
            e1 = r32s(A_ERRHIST + 4)
            e2 = r32s(A_ERRHIST + 8)
            resid = r64s(A_RESID + 0)
            kp, tp, ti, td = ps(P_KP), ps(P_TP), ps(P_TI), ps(P_TD)
            limit, yd, y = ps(P_LIMIT), ps(P_YD), ps(P_Y)
            cmode = list(tgt.read_memory_block8(A_CLOSEMODE, 4))
            ctgt = [r32s(A_CLOSETGT + 4 * i) for i in range(4)]
            pcount = r32s(A_PIDCOUNT + 0)
            vsamp = r8(A_VALIDSMP + 0)
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:6.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue

        num = (e0 - e1) * ti * tp + tp * tp * e0 + td * ti * (e0 - 2 * e1 + e2)
        den = 10 * ti * tp
        calc = tdiv(tdiv(kp * num * 1000, den) + resid, 1000) if den else 0
        note = ""
        if -yd // 2 <= e0 <= yd // 2:
            note, clampd = "死区", 0
        else:
            clampd = max(-limit, min(limit, calc))
            note = "C(限幅)" if clampd != calc else "C"

        act = ""
        if prev_new is not None and new[0] != prev_new[0]:
            d = new[0] - prev_new[0]
            if d > 0:
                acc_o += d
            else:
                acc_c += -d
            act = f"** EEV1 Δ={d:+d} **"
        prev_new = new

        key = (wm, tuple(cs), tuple(new), tuple(old), e0, e1, e2,
               tuple(cmode), tuple(ctgt), vsamp)
        if key != prev or act:
            say("  %5.0f | %-4s | %-9s | %5d %5d %5d %5d %5d | %s | %-11s %s |"
                " %5d %4d | %5d %5d | %s"
                % (el, WM.get(wm, wm),
                   "%s/%s" % (COMP.get(cs[0], cs[0]), COMP.get(cs[1], cs[1])),
                   e0, e1, e2, calc, clampd,
                   " ".join("%d/%d" % (new[i], old[i]) for i in range(NEEV)),
                   "/".join(CLOSE_MODE.get(m, str(m)) for m in cmode),
                   "/".join(str(c) for c in ctgt),
                   pcount, vsamp, acc_o, acc_c, (act + " " + note).strip()))
            prev = key
        time.sleep(0.1)

    if tgt.get_state() == tgt.State.HALTED:
        say("!! 结束 HALTED —— resume")
        tgt.resume()
    say(f"结束 state={tgt.get_state().name}   累计 EEV1 开{acc_o} 步 / 关{acc_c} 步")
    session.close()
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
