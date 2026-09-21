# -*- coding: utf-8 -*-
"""PSC316 外机 EEV 实际步进速率 —— 验规格书 §3.3.5「以 20 步/秒速度关闭」。

## 要回答什么

规格书 §3.3.5：紧急停机「电子膨胀阀以20步/秒速度关闭」。
330 内机有源码可证（`EEVSpecPulseTimeAction()` 按活跃组数把脉冲周期补偿到 10/13/20/32ms，
`Obj/eev.o` 反汇编确认读 `Parameter[860]`）。
**316 外机没有对应补偿**：`eevCTRL.c:558` 每次无条件写 `Parameter[802] = 32`，
驱动 `Obj/eev.o` 确实读它（16 处），但**没有任何按组数缩短周期的代码**。

该板 2 路 EEV 分组轮转（`EEVpriority`/`EEVRunGroup`/`EEVCtrlNum`）。
**若分片占空为 1/2，则单阀 ≈ 32ms×2 → 15.6 步/秒，比规格书慢 22%。**
这个 1/2 只是推算 —— 本脚本就是要把它量出来。

## 为什么不用急停来测

急停的关闭目标是 `当前步数 + 10`，**只有 10 步**（`eevCTRL.c` 的 `EEV_CLOSE_EMERGENCY`），
而且本台面两块 EEV 现在都停在 0 位 ⇒ 拉不出可测的行程。
**改用「手动 EEV」模式拉一条 0→500 的长行程** —— 走的是**同一个 `MTxOutput()` 驱动**，
速率上限完全相同，只是行程长到能量。

## 测法

```
阶段 A：只让 EEV1 动（[156]=1 使能, [155]=500 目标）  → 单阀速率
阶段 B：EEV1+EEV2 一起动（再 [158]=1, [157]=500）      → 双阀速率（验占空 1/2）
复原 ：目标归 0 等到底 → 清 [156]/[158] 使能           → 回到原状
```

SWD 小读约 350 Hz（**别用大块读**，1314B 块读只有 47 Hz）。

## 寄存器（316，`User.h:747-768`）

    EEVPulseTimeSet  Parameter[802]   脉冲周期 ms（驱动读它当节拍闸门）
    EEVCtrlNum       Parameter[804]   当前轮到哪一路（99 = 空闲）
    NewAddValue 805  EEV1New=805 EEV2New=806      指令位置
    OldAddValue 809  EEV1Old=809 EEV2Old=810      当前步数
    EEVRunFlag  813  EEV1Run=813 EEV2Run=814
    Manual      155  [156]/[158]=1 使能手动；[155]/[157]=目标步数

    Parameter[] @ 0x2000164A（`.axf` 符号表取值，已被 Parameter[1000..1005]
    = [316,12,14,2026,9,17] 版本指纹校验）

⚠ `EEVSpecMaxStep()` = clamp(`EEVOpenMaxSizeSet`,200,clamp(`MotorTotalPulseSet`,200,500))
  ⇒ **上限 500**，正是阀门额定全行程。本脚本目标固定 500，不越界。

⚠ **必须 attach**（`connect_mode="attach"`）—— 默认 halt 会把板子冻死。

⚠ 跑之前确认**外机空闲**（`output`/`DA` 全 0、压机没转）。脚本会自检并拒绝在带载时跑。

跑法：
    python.exe tools/probe_316_eev_rate.py              # 阶段A单阀 + 阶段B双阀（手动路径）
    python.exe tools/probe_316_eev_rate.py --emergency  # ★直测急停关闭路径本身
    python.exe tools/probe_316_eev_rate.py --restore    # 只把两块阀关回 0 并解除手动

实测结论（2026-09-21）：
    手动路径  单阀 28.6 步/秒 ／ 双阀同时 14.3~14.6
    急停路径  双阀同时关 **14.4 / 15.0 步/秒**（写 [1406]，两块阀从 410 关到 0）
    ⇒ 规格书 §3.3.5 要 20 步/秒，**慢 25~28%，不符合**。根因是 316 没有
      按活跃组数缩短脉冲周期的补偿，而急停必然同时关两块阀（占空 1/2）。
"""
from __future__ import annotations

import pathlib
import sys
import time

from pyocd.core.helpers import ConnectHelper

OUT = pathlib.Path(__file__).resolve().parent / "probe_316_eev_rate.txt"

PB = 0x2000164A                 # Parameter[]
OUT_BASE = 0x200000D4           # output[8]  Y00..Y07
DA_BASE = 0x20000016            # DA[2]

I_PULSE = 802
I_CTRLNUM = 804
I_MANUAL = 155                  # [155]/[157] 目标, [156]/[158] 使能
I_MAXPULSE = 10                 # MotorTotalPulseSet
I_OPENMAX = 12                  # EEVOpenMaxSizeSet
I_URG = 1406                    # UrgencyStop（330 经 RS485 下发的就是它）
OPEN_TO = 400                   # 急停实测前先把阀顶到这个开度
N_EEV = 2
NEW = lambda i: 805 + i         # noqa: E731
OLD = lambda i: 809 + i         # noqa: E731
RUNF = lambda i: 813 + i        # noqa: E731
TGT = lambda i: 155 + 2 * i     # noqa: E731
ENA = lambda i: 156 + 2 * i     # noqa: E731

TARGET = 500
# 版本指纹不再精确匹配 —— 否则每次拨版本号（本仓惯例）都要改探针。
# 只校验「型号=316、大版本=12、日期落在合理区间」，既能挡住基址错，又不会绊自己。
FP_MODEL, FP_MAJOR = 316, 12


def fp_ok(fp) -> bool:
    if len(fp) != 6 or fp[0] != FP_MODEL or fp[1] != FP_MAJOR:
        return False
    y, m, d = fp[3], fp[4], fp[5]
    return 2024 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode("gbk", "replace").decode("gbk", "replace"), flush=True)


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class B:
    def __init__(self, tgt):
        self.t = tgt

    def p(self, i):
        return s16(int.from_bytes(bytes(self.t.read_memory_block8(PB + 2 * i, 2)), "little"))

    def pl(self, a, n):
        b = bytes(self.t.read_memory_block8(PB + 2 * a, 2 * n))
        return [s16(int.from_bytes(b[2 * k:2 * k + 2], "little")) for k in range(n)]

    def wp(self, i, v):
        self.t.write_memory_block8(PB + 2 * i, bytes([v & 0xFF, (v >> 8) & 0xFF]))

    def out_da(self):
        o = list(bytes(self.t.read_memory_block8(OUT_BASE, 8)))
        dw = bytes(self.t.read_memory_block8(DA_BASE, 4))
        return o, [int.from_bytes(dw[2 * k:2 * k + 2], "little") for k in range(2)]


def measure(bd, moving, seconds, label):
    """轮询各通道 OldAddValue + EEVCtrlNum。moving = 本阶段真正在动的通道。

    返回 [(t, [old0, old1], ctrl), ...]
    """
    say("  %s：轮询 OldAddValue[0,1] + EEVCtrlNum，最多 %.0fs（在动的通道到底即停）"
        % (label, seconds))
    t0 = time.time()
    samples = []
    while time.time() - t0 < seconds:
        ts = time.time() - t0
        vals = [bd.p(OLD(0)), bd.p(OLD(1))]
        ctrl = bd.p(I_CTRLNUM)
        samples.append((ts, vals, ctrl))
        if moving and all(vals[c] >= TARGET for c in moving):
            break
        if not moving and vals[0] > 0 and vals[0] == vals[1]:
            break
    say("    采 %d 拍，时长 %.1fs" % (len(samples), samples[-1][0] if samples else 0))
    return samples


def rate_of(samples, k):
    """按「每个新数值首次出现的时刻」算步进周期 —— 这才是真正的单步间隔。

    ⚠ 不能用相邻采样的时间差：采样 ~1.5ms 远快于步进（~90ms），
      会得出"单步间隔 = 采样间隔"的假值（第一版就是这么错的）。
    """
    if not samples:
        return None
    # 折叠成 [(t, value), ...]，每个数值只留首次出现的时刻
    steps = []
    for row in samples:
        ts, v = row[0], row[1]
        if not steps or v[k] != steps[-1][1]:
            steps.append((ts, v[k]))
    if len(steps) < 3:
        return None
    # 找最长的一段单调段 —— **两个方向都要试**：
    # 手动开阀是升，急停关闭是**降**（第一版只找升，急停那轮全判成"没有有效位移"）。
    best = (0, 0, 0)
    for sign in (+1, -1):
        i = 0
        while i < len(steps) - 1:
            j = i
            while (j < len(steps) - 1 and
                   sign * (steps[j + 1][1] - steps[j][1]) >= -1):
                j += 1
            if j - i > best[2]:
                best = (i, j, j - i)
            i = j + 1 if j > i else i + 1
    i, j, _ = best
    if j - i < 3:
        return None
    span = [s for s in steps[i:j + 1]]
    dt = span[-1][0] - span[0][0]
    dn = abs(span[-1][1] - span[0][1])          # ⚠ 关闭时是负增量，必须取绝对值
    if dt <= 0 or dn <= 0:
        return None
    periods = sorted(span[m + 1][0] - span[m][0] for m in range(len(span) - 1))
    return {"rate": dn / dt, "dn": dn, "dt": dt,
            "start": span[0][1], "end": span[-1][1],
            "periods": periods, "n": len(span)}


def ctrl_hist(samples):
    """EEVCtrlNum 的取值分布 —— 用来判断轮转占空。"""
    import collections
    c = collections.Counter(x[2] for x in samples)
    tot = sum(c.values())
    return [(k, v, v * 100.0 / tot) for k, v in sorted(c.items(), key=lambda x: -x[1])]


def main() -> int:
    restore_only = "--restore" in sys.argv

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        say("✗ 连不上 ST-Link")
        OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        return 1

    with session:
        t = session.target
        bd = B(t)
        say("=== PSC316 外机 EEV 实际步进速率 ===")
        say("内核 = %s" % t.get_state())
        if t.get_state() == t.State.HALTED:
            say("!! HALTED，立刻 resume")
            t.resume()
            say("   resume 后 = %s" % t.get_state())
        say()

        # ---------- 基址自检 ----------
        fp = bd.pl(1000, 6)
        say("基址自检 Parameter[1000..1005] = %s" % fp)
        if not fp_ok(fp):
            say("✗ 指纹不像 316 V12.x（模型%d/大版本%d），⇒ Parameter[] 基址不对或挂错板，"
                "退出，不写任何东西。" % (FP_MODEL, FP_MAJOR))
            OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
            return 1
        say("   版本指纹通过：PSC316 V%d.%d / %d-%d-%d" % (fp[1], fp[2], fp[3], fp[4], fp[5]))
        say()

        maxp, openmax = bd.p(I_MAXPULSE), bd.p(I_OPENMAX)
        say("MotorTotalPulseSet[%d]=%d  EEVOpenMaxSizeSet[%d]=%d  ⇒ 上限 500"
            % (I_MAXPULSE, maxp, I_OPENMAX, openmax))
        say("EEVPulseTimeSet[%d]=%d ms   EEVCtrlNum[%d]=%d   （99=空闲）"
            % (I_PULSE, bd.p(I_PULSE), I_CTRLNUM, bd.p(I_CTRLNUM)))
        say()

        # ---------- 原始状态 ----------
        orig = {
            "ena": [bd.p(ENA(i)) for i in range(N_EEV)],
            "tgt": [bd.p(TGT(i)) for i in range(N_EEV)],
            "new": [bd.p(NEW(i)) for i in range(N_EEV)],
            "old": [bd.p(OLD(i)) for i in range(N_EEV)],
            "runf": [bd.p(RUNF(i)) for i in range(N_EEV)],
        }
        o, da = bd.out_da()
        say("--- 原始状态 ---")
        say("  Manual 使能 %s  目标 %s" % (orig["ena"], orig["tgt"]))
        say("  EEV New %s   Old(当前步数) %s   RunFlag %s"
            % (orig["new"], orig["old"], orig["runf"]))
        say("  output[8] = %s   DA[2] = %s" % (o, da))
        if any(o) or any(da):
            say("  ✗ 外机**带载**（output/DA 非 0）—— 不要在压机/风机运行时动手动 EEV。退出。")
            OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
            return 2
        say("  ✓ 外机空闲（output/DA 全 0）")
        say()

        if "--emergency" in sys.argv:
            # ============ 直接量「急停关闭」这条路径本身 ============
            # 手动模式只是「千斤顶」：把两块阀顶到 400，好让急停有行程可关。
            # 触发用写 [1406] UrgencyStop=1 —— 正是 330 经 RS485 下发的那一个寄存器，
            # 也是 316/eevCTRL.c 急停分支的入口。
            say("############ 急停路径直接实测 ############")
            say("  先手动把两块阀顶到 %d（急停的目标只有 当前+10 步，必须先把阀打开）" % OPEN_TO)
            for i in range(N_EEV):
                bd.wp(TGT(i), OPEN_TO)
                bd.wp(ENA(i), 1)
            t0 = time.time()
            while time.time() - t0 < 90:
                if bd.p(OLD(0)) >= OPEN_TO and bd.p(OLD(1)) >= OPEN_TO:
                    break
                time.sleep(0.2)
            say("  顶到位：Old=[%d,%d]（%.1fs）Manual 使能=[%d,%d]"
                % (bd.p(OLD(0)), bd.p(OLD(1)), time.time() - t0,
                   bd.p(ENA(0)), bd.p(ENA(1))))
            say("  ⚠ 保持手动使能 —— 否则空闲机组的正常控制会先把手动接管掉，")
            say("     量到的就是普通关闭（+20）而不是急停关闭（+10）。")
            say()
            say("  >>> 写 [%d] UrgencyStop = 1" % I_URG)
            t_trig = time.time()
            bd.wp(I_URG, 1)
            # --pulse=N：急停期间把 [802] 改成 N，验"周期是瓶颈"这个假设。
            # 能这么干是因为急停分支在 :723 就 return 了 ⇒ EEV_Action(0) 不会执行
            # ⇒ :558 那句写死 32 的语句这一轮根本不会跑 ⇒ 我写的值留得住。
            pulse = None
            for a in sys.argv[1:]:
                if a.startswith("--pulse="):
                    pulse = int(a.split("=", 1)[1])
            if pulse is not None:
                say("      ⚠ --pulse=%d：把 [%d] 从 %d 改成 %d（330 的补偿在 2 组时正是 20）"
                    % (pulse, I_PULSE, bd.p(I_PULSE), pulse))
                bd.wp(I_PULSE, pulse)
            say("      回读 [%d]=%d  [802]EEVPulseTimeSet=%d  [605]?=%d"
                % (I_URG, bd.p(I_URG), bd.p(I_PULSE), bd.p(605)))
            tgt_seen = [bd.p(NEW(0)), bd.p(NEW(1))]
            say("      下发后 New=[%d,%d]（应为 当前步数+10 再逐拍 -20）" % tuple(tgt_seen))
            say()
            # --hold：每拍重写 [1406]=1（防被 330 经 RS485 盖掉）与 [802]=pulse
            #   ⚠ 实测踩过：316 自己不写 UrgencyStop，是 **330 周期性地把 0 写回来**
            #     （`modulecontrol.c:1111-1115` 那条下发链），急停会在十几秒后中途解除
            #     ⇒ `EEV_ActionAll` 转正常分支 ⇒ `:558` 把 [802] 写回 32
            #     ⇒ 量到的就不是纯急停路径了。
            hold = "--hold" in sys.argv
            samples = []
            while time.time() - t_trig < 90:
                if hold:
                    bd.wp(I_URG, 1)
                    if pulse is not None:
                        bd.wp(I_PULSE, pulse)
                ts = time.time() - t_trig
                samples.append((ts, [bd.p(OLD(0)), bd.p(OLD(1))], bd.p(I_CTRLNUM)))
                samples[-1] = samples[-1] + (bd.p(I_URG), bd.p(I_PULSE))
                if samples[-1][1][0] <= 0 and samples[-1][1][1] <= 0:
                    break
            say("  采 %d 拍，时长 %.1fs"
                % (len(samples), samples[-1][0] if samples else 0))
            # ⚠ 必须报**关闭过程中**的 [802]，不能报结束后的当前值 ——
            #   急停一结束补偿就回到 32（0 组活跃），报当前值会得出"周期没变"的错结论。
            if samples and len(samples[0]) >= 5:
                pu = [s[4] for s in samples]
                ug = [s[3] for s in samples]
                seen = sorted(set(pu))
                say("  关闭过程中 [802] 取值：%s   （其它值占比 %.0f%%）"
                    % (seen, 100.0 * sum(1 for x in pu if x != seen[0]) / len(pu))
                    if len(seen) > 1 else
                    "  关闭过程中 [802] 恒为 %d ms" % seen[0])
                say("  关闭过程中 [1406]=1 占比 %.0f%%" % (100.0 * sum(1 for x in ug if x == 1) / len(ug)))
            say("  关到底：Old=[%d,%d]  [1406]=%d"
                % (bd.p(OLD(0)), bd.p(OLD(1)), bd.p(I_URG)))
            say()
            say("=== 急停关闭速率（规格书 §3.3.5 要 20 步/秒）===")
            say("  【急停】EEVCtrlNum 分布：%s"
                % "  ".join("%s占 %.1f%%" % (k, q) for k, _, q in ctrl_hist(samples)))
            for k in range(N_EEV):
                r = rate_of(samples, k)
                if r is None:
                    say("    EEV%d：没有有效位移" % (k + 1))
                    continue
                p = r["periods"]
                say("    EEV%d：%d → %d（%d 步 / %.2fs）= **%.1f 步/秒**  %s"
                    % (k + 1, r["start"], r["end"], r["dn"], r["dt"], r["rate"],
                       "符合 20" if abs(r["rate"] - 20) <= 2 else
                       ("**慢 %.0f%%**" % ((1 - r["rate"] / 20) * 100) if r["rate"] < 20
                        else "**快 %.0f%%**" % ((r["rate"] / 20 - 1) * 100))))
                say("        单步周期：中位 %.1f ms（最小 %.1f / 最大 %.1f）"
                    % (p[len(p) // 2] * 1000, p[0] * 1000, p[-1] * 1000))
            say()
            say("--- 复原：清 [1406] → 清手动 ---")
            bd.wp(I_URG, 0)
            for i in range(N_EEV):
                bd.wp(ENA(i), 0)
                bd.wp(TGT(i), 0)
            time.sleep(1.0)
            say("  [1406]=%d  Manual=[%d,%d]  Old=[%d,%d]  New=[%d,%d]"
                % (bd.p(I_URG), bd.p(ENA(0)), bd.p(ENA(1)),
                   bd.p(OLD(0)), bd.p(OLD(1)), bd.p(NEW(0)), bd.p(NEW(1))))
            if t.get_state() == t.State.HALTED:
                say("  !! HALTED，resume")
                t.resume()
            say("  内核 = %s" % t.get_state())
            OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
            print("\n→ %s" % OUT)
            return 0

        if restore_only:
            say("--- --restore：目标归 0 → 等到底 → 解除手动 ---")
            for i in range(N_EEV):
                bd.wp(TGT(i), 0)
                bd.wp(ENA(i), 1)
            t0 = time.time()
            while time.time() - t0 < 60:
                if all(bd.p(OLD(i)) <= 0 for i in range(N_EEV)):
                    break
                time.sleep(0.5)
            for i in range(N_EEV):
                bd.wp(ENA(i), 0)
            say("  EEV Old = %s   Manual 使能 = %s"
                % (bd.pl(OLD(0), N_EEV), bd.pl(ENA(0), N_EEV)))
            OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
            return 0

        # ---------- 阶段 A：单阀 ----------
        say("############ 阶段 A：只动 EEV1 ############")
        say("  写 [%d]=1 使能手动，[%d]=%d 目标" % (ENA(0), TGT(0), TARGET))
        bd.wp(TGT(0), TARGET)
        bd.wp(ENA(0), 1)
        time.sleep(0.2)
        say("  使能后回读：[%d]=%d  New[%d]=%d  Old[%d]=%d"
            % (ENA(0), bd.p(ENA(0)), NEW(0), bd.p(NEW(0)), OLD(0), bd.p(OLD(0))))
        say("  EEVCtrlNum=%d" % bd.p(I_CTRLNUM))
        sA = measure(bd, [0], 45, "A")
        out, da = bd.out_da()
        if any(out) or any(da):
            say("  ⚠ 期间外机起载了（output=%s DA=%s）—— 数据可能受正常控制律干扰" % (out, da))
        say()

        # ---------- 阶段 B：双阀 ----------
        say("############ 阶段 B：EEV1 + EEV2 **同时**动 ############")
        say("  ⚠ 第一版这里漏了：EEV1 在阶段 A 已经到 500，所以 B 里只有 EEV2 在动，")
        say("     EEVCtrlNum 全程=1 —— **两块阀从没同时运动过**，占空问题没验到。")
        say("  先两块都关回 0，再同一瞬间给两块下目标。")
        for i in range(N_EEV):
            bd.wp(TGT(i), 0)
            bd.wp(ENA(i), 1)
        t0 = time.time()
        while time.time() - t0 < 60:
            if bd.p(OLD(0)) <= 0 and bd.p(OLD(1)) <= 0:
                break
            time.sleep(0.2)
        say("  归零后 Old=[%d,%d]（用时 %.1fs）"
            % (bd.p(OLD(0)), bd.p(OLD(1)), time.time() - t0))
        say("  >>> 同一瞬间写 [%d]=%d 和 [%d]=%d" % (TGT(0), TARGET, TGT(1), TARGET))
        bd.wp(TGT(0), TARGET)
        bd.wp(TGT(1), TARGET)
        st = bd.p(I_CTRLNUM)
        say("  下发后立刻：New=[%d,%d]  Old=[%d,%d]  EEVCtrlNum=%d"
            % (bd.p(NEW(0)), bd.p(NEW(1)), bd.p(OLD(0)), bd.p(OLD(1)), st))
        sB = measure(bd, [0, 1], 120, "B")
        say()

        # ---------- 报告 ----------
        say("=== 速率计算 ===")
        for tag, s in (("A 单阀", sA), ("B 双阀", sB)):
            say("  【%s】EEVCtrlNum 分布：%s"
                % (tag, "  ".join("%s占 %.1f%%" % (k, p) for k, _, p in ctrl_hist(s))))
            for k in range(N_EEV):
                r = rate_of(s, k)
                if r is None:
                    say("    EEV%d：没有有效位移（该通道本阶段没动）" % (k + 1))
                    continue
                p = r["periods"]
                say("    EEV%d：%d → %d（%d 步 / %.2fs）= **%.1f 步/秒**"
                    % (k + 1, r["start"], r["end"], r["dn"], r["dt"], r["rate"]))
                say("        单步周期：中位 **%.1f ms**（最小 %.1f / 最大 %.1f，%d 个）"
                    % (p[len(p) // 2] * 1000, p[0] * 1000, p[-1] * 1000, len(p)))
        say()

        say("=== 对照规格书 §3.3.5「以 20 步/秒速度关闭」===")
        ra = rate_of(sA, 0)
        rb0, rb1 = rate_of(sB, 0), rate_of(sB, 1)
        if ra:
            say("  单阀 %.1f 步/秒  vs 20  →  %s"
                % (ra["rate"],
                   "符合" if abs(ra["rate"] - 20) <= 2 else
                   "**偏慢 %.0f%%**" % ((1 - ra["rate"] / 20) * 100) if ra["rate"] < 20 else
                   "**偏快 %.0f%%**" % ((ra["rate"] / 20 - 1) * 100)))
        if rb0 and ra:
            say("  双阀 %.1f / %.1f 步/秒  →  相对单阀比 %.2f（若 ≈0.5 即证实「分片占空 1/2」）"
                % (rb0["rate"], rb1["rate"] if rb1 else -1, rb0["rate"] / ra["rate"]))
        say("  （急停关闭走同一 `MTxOutput()` 驱动 ⇒ 驱动上限相同；此速率即急停速率的上限）")
        say()

        # ---------- 复原 ----------
        say("--- 复原：目标归 0 → 等到底 → 解除手动 ---")
        for i in range(N_EEV):
            bd.wp(TGT(i), 0)
            bd.wp(ENA(i), 1)
        t0 = time.time()
        while time.time() - t0 < 60:
            if all(bd.p(OLD(i)) <= 0 for i in range(N_EEV)):
                break
            time.sleep(0.5)
        for i in range(N_EEV):
            bd.wp(ENA(i), 0)
        say("  Old = %s   New = %s   Manual 使能 = %s"
            % (bd.pl(OLD(0), N_EEV), bd.pl(NEW(0), N_EEV), bd.pl(ENA(0), N_EEV)))
        say("  原始 Old 是 %s" % orig["old"])
        if t.get_state() == t.State.HALTED:
            say("  !! HALTED，resume")
            t.resume()
        say("  内核 = %s" % t.get_state())

    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
