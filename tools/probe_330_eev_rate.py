# -*- coding: utf-8 -*-
"""PSC330 内机 EEV 实际步进速率 —— 补上 §3.3.5/§3.9「20 步/秒」在**内机侧**的实测。

## 为什么现在才做

316 外机侧 2026-09-21 已实测（`probe_316_eev_rate.py` + `V12.17` 补偿）。
330 侧一直只有**推算**：它源码里有 `EEVSpecPulseTimeAction()`（按活跃组数把周期
调到 10/13/20/32ms），而且 `Obj/eev.o` 反汇编确认会读 `Parameter[860]`
—— 但**驱动对同一参数有两种闸门**（`eev.c:318` 用 `EEVPulseTimeSet+100`、
`:322` 用 `EEVPulseTimeSet`），走哪条取决于子状态。**所以实际速率只能实测。**

## 330 与 316 的结构差别

    330：8 路 = **4 组**，每组 2 路（MT1&MT5 同组、MT2&MT6、MT3&MT7、MT4&MT8，见 eev.c:267/483/699/914…）
         同一组的两路在**同一个 1.3s 时间片内并发**步进
    316：2 路 = 2 组，每条时间片 1 路

    所以 330 的模型是：速率 = 1000 / (脉冲 × 活跃组数)
        1 组 → 32ms → ~31/s    2 组 → 20ms → ~25/s    4 组 → 10ms → ~25/s
    ⚠ 但 `+100` 那条件若被走到，速率会掉到几分之一 —— 这正是要量的。

## 寄存器（330，`User/UserHead/User.h`）

    EEVPulseTimeSet  Parameter[860]    脉冲周期（330 用 860，**不是** 316 的 802！）
    EEVCtrlNum       Parameter[1144]   当前轮到哪一组（99=空闲）
    NewAddValue 1145 EEV1..8New = 1145..1152
    OldAddValue 1153 EEV1..8Old = 1153..1160     ← 步进计数器，被测对象
    EEVRunFlag  1161
    Manual      220  [221]/[223]/…=1 使能；[220]/[222]/…=目标步数
    ValveLinkFaultLatchDisp Parameter[962]       ← 触发急停（写 1）
    Parameter[] @ 0x200030C8

## 测法

    ① 手动模式把 EEV1（组0）与 EEV2（组1）顶到 400，当"千斤顶"造出行程
       ⚠ 保持手动使能，否则正常控制会先接管
    ② 写 [962]=1 触发急停（**不能直接写 [1406]** —— `ErrorCheck.c:607` 每扫描把它清 0）
    ③ 高频读 OldAddValue[1153..1160]，同时读 [860] 看补偿给了多少
    ④ 复原：清 [962] → 清手动 → 关回 0

跑法： python.exe tools/probe_330_eev_rate.py
"""
from __future__ import annotations

import pathlib
import sys
import time

from pyocd.core.helpers import ConnectHelper

OUT = pathlib.Path(__file__).resolve().parent / "probe_330_eev_rate.txt"

PB = 0x200030C8
OUT_BASE = 0x20001364          # output[16]
DA_BASE = 0x20001872           # DA[10]

I_PULSE = 860
I_CTRLNUM = 1144
I_VLATCH = 962                 # 触发
I_HANDDEBUG = 1300             # HandD=1300，手动调试模式门禁（300 秒超时）
I_MAXPULSE = 10                # MotorTotalPulseSet
I_OPENMAX = 12                 # EEVOpenMaxSizeSet
NEW = lambda i: 1145 + i       # noqa: E731
OLD = lambda i: 1153 + i       # noqa: E731
RUNF = lambda i: 1161 + i      # noqa: E731
TGT = lambda i: 220 + 2 * i    # noqa: E731
ENA = lambda i: 221 + 2 * i    # noqa: E731

OPEN_TO = 400
N8 = 8
TEST = (0, 1, 2, 3)            # 4 个组各一路 ⇒ activeGroups=4（真实急停工况）

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode("gbk", "replace").decode("gbk", "replace"), flush=True)


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class B:
    def __init__(self, t):
        self.t = t

    def p(self, i):
        return s16(int.from_bytes(bytes(self.t.read_memory_block8(PB + 2 * i, 2)), "little"))

    def pl(self, a, n):
        b = bytes(self.t.read_memory_block8(PB + 2 * a, 2 * n))
        return [s16(int.from_bytes(b[2 * k:2 * k + 2], "little")) for k in range(n)]

    def wp(self, i, v):
        self.t.write_memory_block8(PB + 2 * i, bytes([v & 0xFF, (v >> 8) & 0xFF]))

    def io(self):
        o = list(bytes(self.t.read_memory_block8(OUT_BASE, 16)))
        dw = bytes(self.t.read_memory_block8(DA_BASE, 20))
        return o, [int.from_bytes(dw[2 * k:2 * k + 2], "little") for k in range(10)]


def mono_rate(steps):
    if len(steps) < 3:
        return None
    best = (0, 0)
    i = 0
    while i < len(steps) - 1:
        j = i
        while j < len(steps) - 1 and (steps[j + 1][1] - steps[j][1]) <= 1:
            j += 1
        if j - i > best[1] - best[0]:
            best = (i, j)
        i = j + 1 if j > i else i + 1
    a, b = best
    if b - a < 3:
        return None
    span = steps[a:b + 1]
    dt = span[-1][0] - span[0][0]
    dn = abs(span[-1][1] - span[0][1])
    if dt <= 0 or dn <= 0:
        return None
    per = sorted(span[m + 1][0] - span[m][0] for m in range(len(span) - 1))
    return {"from": span[0][1], "to": span[-1][1], "dn": dn, "dt": dt,
            "rate": dn / dt, "med": per[len(per) // 2]}


def main() -> int:
    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f407ze",
        options={"frequency": 1000000, "connect_mode": "attach"})
    if session is None:
        say("✗ 连不上 ST-Link"); return 1
    with session:
        t = session.target
        b = B(t)
        say("=== PSC330 内机 EEV 实际步进速率（急停关闭）===")
        say("内核 = %s" % t.get_state())
        if t.get_state() == t.State.HALTED:
            t.resume(); say("  已 resume")

        o, da = b.io()
        say("output 非零位 = %s   DA = %s" % ([i for i, x in enumerate(o) if x], da))
        if any(o) or any(da):
            say("✗ 机组带载，退出（不在带载时动手动 EEV）"); return 2
        say("机组空闲 ✓  [236]模式=%d  [709]SysStep=%d" % (b.p(236), b.p(709)))
        say("MotorTotalPulseSet[%d]=%d  EEVOpenMaxSizeSet[%d]=%d"
            % (I_MAXPULSE, b.p(I_MAXPULSE), I_OPENMAX, b.p(I_OPENMAX)))
        say("New[1145..1152] = %s" % b.pl(NEW(0), N8))
        say("Old[1153..1160] = %s" % b.pl(OLD(0), N8))
        say()

        # ⚠ 330 的手动 EEV 有一道硬门禁（`eevCTRL.c:450-456`，20251030 加的）：
        #     manualAllowed = (HandDebug==1) && (SysStep==0) && (SysErrStatus==0) &&
        #                     (!IndoorSensorPartialStopFlag) && 通讯故障全 0
        #   不置 HandDebug=1 的话，`HandDebugY02Ctrl`（UserAction.c:3344）每扫描把
        #   `Parameter[Manual+1+2*i]` 清 0 —— 实测写 [221]=1 立刻被清回 0，阀一动不动。
        #   而且 HandDebug 有 **300 秒超时**（UserAction.c:3354），得在这个窗口内干完。
        say("--- 先开手动调试门禁 HandDebug[%d]=1 ---" % I_HANDDEBUG)
        say("  门禁现值：SysStep[709]=%d  SystemComErr[611]=%d  COMP1..4ComErr=%s"
            % (b.p(709), b.p(611), b.pl(594, 4)))
        b.wp(I_HANDDEBUG, 1)
        time.sleep(0.3)
        say("  写后回读 HandDebug=%d  %s"
            % (b.p(I_HANDDEBUG), "OK" if b.p(I_HANDDEBUG) == 1 else "**没留住**"))
        say()

        say("--- 手动把 EEV%s 顶到 %d（千斤顶）---" % (list(x + 1 for x in TEST), OPEN_TO))
        for i in TEST:
            b.wp(TGT(i), OPEN_TO); b.wp(ENA(i), 1)
        t0 = time.time()
        while time.time() - t0 < 120:
            if all(b.p(OLD(i)) >= OPEN_TO for i in TEST):
                break
            time.sleep(0.2)
        say("  到位 Old=%s（%.1fs）Manual=%s"
            % (b.pl(OLD(0), 4), time.time() - t0, b.pl(ENA(0), 4)))
        say()

        say("--- 写 [%d] ValveLinkFaultLatchDisp=1 触发急停 ---" % I_VLATCH)
        b.wp(I_VLATCH, 1)
        t_trig = time.time()
        samples = []
        while time.time() - t_trig < 120:
            ts = time.time() - t_trig
            samples.append((ts, b.pl(OLD(0), 4), b.p(I_PULSE), b.p(I_CTRLNUM)))
            if all(v <= 0 for v in samples[-1][1]):
                break
            time.sleep(0.004)
        say("  采 %d 拍 %.1fs" % (len(samples), samples[-1][0]))
        pu = [x[2] for x in samples]
        say("  过程中 [860] 取值：%s" % sorted(set(pu)))
        say("  [962]=%d  [1406]=%d" % (b.p(I_VLATCH), b.p(1406)))
        say("  Old[1153..1160] 收尾 = %s" % b.pl(OLD(0), N8))
        say()

        say("=== 速率（规格书 §3.3.5/§3.9 要 20 步/秒）===")
        import collections
        c = collections.Counter(x[3] for x in samples)
        tot = sum(c.values())
        say("  EEVCtrlNum 分布：%s"
            % "  ".join("%s占%.1f%%" % (k, v * 100.0 / tot) for k, v in c.most_common(5)))
        for k in TEST:
            steps = []
            for row in samples:
                if not steps or row[1][k] != steps[-1][1]:
                    steps.append((row[0], row[1][k]))
            r = mono_rate(steps)
            if r is None:
                say("  EEV%d：没有有效位移" % (k + 1)); continue
            say("  EEV%d：%d → %d（%d 步 / %.2fs）= **%.1f 步/秒**  单步周期中位 %.1f ms  %s"
                % (k + 1, r["from"], r["to"], r["dn"], r["dt"], r["rate"], r["med"] * 1000,
                   "符合 20" if abs(r["rate"] - 20) <= 2 else
                   ("**慢 %.0f%%**" % ((1 - r["rate"] / 20) * 100) if r["rate"] < 20
                    else "**快 %.0f%%**" % ((r["rate"] / 20 - 1) * 100))))
        say("  （活动组数：只顶了 EEV1/EEV2 ⇒ 组0 与 组1 ⇒ activeGroups=2 ⇒ 预期周期 20ms）")
        say()

        say("--- 复原 ---")
        # ⚠ 急停会在 330 留下**锁存故障**：写 [962] -> EnviTempErr[605]=1 -> SysErrStatus[710]=1，
        #   而 SysErrStatus 会卡住 manualAllowed，下次再也进不了手动模式（第一轮就吃了这个亏）。
        #   ErrorCheck.c:582 每扫描先清 0，所以只要把源头清掉它就自己回 0。
        b.wp(I_VLATCH, 0)
        for i in (605, 960, 964):
            b.wp(i, 0)
        for i in range(N8):
            b.wp(ENA(i), 0)
        for i in TEST:
            b.wp(TGT(i), 0); b.wp(ENA(i), 1)
        t0 = time.time()
        while time.time() - t0 < 90:
            if all(b.p(OLD(i)) <= 0 for i in TEST):
                break
            time.sleep(0.3)
        for i in range(N8):
            b.wp(ENA(i), 0)
        b.wp(I_HANDDEBUG, 0)          # 关掉手动调试门禁
        time.sleep(0.5)
        say("  [962]=%d [605]=%d [710]SysErrStatus=%d [1406]=%d HandDebug=%d Manual=%s Old=%s"
            % (b.p(I_VLATCH), b.p(605), b.p(710), b.p(1406), b.p(I_HANDDEBUG),
               b.pl(ENA(0), 2), b.pl(OLD(0), 2)))
        if t.get_state() == t.State.HALTED:
            t.resume(); say("  !! HALTED，已 resume")
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
