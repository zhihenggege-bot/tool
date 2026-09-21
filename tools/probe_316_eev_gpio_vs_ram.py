# -*- coding: utf-8 -*-
"""PSC316 EEV：**GPIO 引脚相位 vs RAM 步进计数器** 对照 —— 回答"我测的到底是不是引脚脉冲"。

## 为什么要做

`probe_316_eev_rate.py` 测的速率是从 `Parameter[OldAddValue+i]`（`[809]`/`[810]`）来的，
那是**软件计数器**。它与引脚实际输出的脉冲是不是 1:1，属于**推断**，不是实测。

本项目有前科：Y15/Y16 那次就是「RAM 里看着在翻转，引脚其实是恒定的」
（见 调试记录 §26 / §28）—— 大忌是**拿 RAM 瞬态当引脚翻转**。

所以这里**同时**采两样东西，直接对账：

    RAM : Parameter[809] / Parameter[810]        步进计数器
    GPIO: GPIOC/GPIOD/GPIOB 的 ODR 位             电机相位（4 线 × 2 阀）

**判据**：同一段时间里，某块阀的 **RAM 减量** 与 **GPIO 相位跳变次数** 是否相等。

## 引脚（`WELLTHINKER/EEV/eev.h`）

    EEV1/MT1:  A=GPIOD.15  B=GPIOD.14  RA=GPIOC.7  RB=GPIOC.6
    EEV2/MT2:  A=GPIOD.1   B=GPIOD.0   RA=GPIOB.4  RB=GPIOD.4

    GPIOB ODR 0x40010C0C   GPIOC ODR 0x4001100C   GPIOD ODR 0x4001140C

⚠ `eev.h` 里 `MT1_A_H()` 用的是 `BRR`（**清零**），命名和电平是反的 —— 所以本脚本只比
  **相位图案有没有变化**，不解释高低电平，免得被这套命名绕进去。

## 行程怎么造

同 `probe_316_eev_rate.py`：手动 EEV 当"千斤顶"把两块阀顶到 400（保持手动使能），
再写 `[1406] UrgencyStop=1` 触发急停关闭。跑之前自检外机空闲。

跑法： python.exe tools/probe_316_eev_gpio_vs_ram.py
"""
from __future__ import annotations

import pathlib
import sys
import time

from pyocd.core.helpers import ConnectHelper

OUT = pathlib.Path(__file__).resolve().parent / "probe_316_eev_gpio_vs_ram.txt"

PB = 0x2000164A
OUT_BASE = 0x200000D4
I_PULSE, I_CTRLNUM, I_URG = 802, 804, 1406
NEW = lambda i: 805 + i          # noqa: E731
OLD = lambda i: 809 + i          # noqa: E731
TGT = lambda i: 155 + 2 * i      # noqa: E731
ENA = lambda i: 156 + 2 * i      # noqa: E731
OPEN_TO = 400

GPIOB_ODR = 0x40010C0C
GPIOC_ODR = 0x4001100C
GPIOD_ODR = 0x4001140C
# (port_addr, bit) × 4，顺序 A,B,RA,RB
PINS = {
    0: ((GPIOD_ODR, 15), (GPIOD_ODR, 14), (GPIOC_ODR, 7), (GPIOC_ODR, 6)),
    1: ((GPIOD_ODR, 1), (GPIOD_ODR, 0), (GPIOB_ODR, 4), (GPIOD_ODR, 4)),
}

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

    def wp(self, i, v):
        self.t.write_memory_block8(PB + 2 * i, bytes([v & 0xFF, (v >> 8) & 0xFF]))

    def odr(self, addr, n=1):
        return bytes(self.t.read_memory_block8(addr, n))

    def sample(self, odrs):
        """一次采：两块阀的 RAM 计数 + 两块阀的 4 线相位图案。"""
        old = [self.p(OLD(0)), self.p(OLD(1))]
        for a in (GPIOB_ODR, GPIOC_ODR, GPIOD_ODR):
            odrs[a] = int.from_bytes(self.odr(a, 4), "little")
        pat = []
        for i in (0, 1):
            v = 0
            for k, (addr, bit) in enumerate(PINS[i]):
                v |= ((odrs[addr] >> bit) & 1) << k
            pat.append(v)
        return old, pat


def mono_rate(steps):
    """steps = [(t, value)]，取最长单调递减段算速率。"""
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
    return {"from": span[0][1], "to": span[-1][1], "dn": dn, "dt": dt, "rate": dn / dt}


def main() -> int:
    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"})
    if session is None:
        say("✗ 连不上 ST-Link"); return 1
    with session:
        t = session.target
        b = B(t)
        say("=== 316 EEV：GPIO 引脚相位 vs RAM 步进计数器 ===")
        say("内核 = %s" % t.get_state())
        if t.get_state() == t.State.HALTED:
            t.resume(); say("  已 resume")
        fp = [b.p(1000 + k) for k in range(6)]
        say("版本指纹 = %s" % fp)
        if fp[0] != 316:
            say("✗ 不像 316，退出"); return 1
        o = list(b.odr(OUT_BASE, 8))
        if any(o):
            say("✗ 外机带载 output=%s，退出（不在带载时动手动 EEV）" % o); return 2
        say("外机空闲 output=%s" % o)
        say()

        say("--- 用手动模式把两块阀顶到 %d（千斤顶）---" % OPEN_TO)
        for i in (0, 1):
            b.wp(TGT(i), OPEN_TO); b.wp(ENA(i), 1)
        t0 = time.time()
        while time.time() - t0 < 90:
            if b.p(OLD(0)) >= OPEN_TO and b.p(OLD(1)) >= OPEN_TO:
                break
            time.sleep(0.2)
        say("  到位 Old=[%d,%d]（%.1fs）Manual=[%d,%d]"
            % (b.p(OLD(0)), b.p(OLD(1)), time.time() - t0, b.p(ENA(0)), b.p(ENA(1))))
        say()

        say("--- 写 [%d] UrgencyStop=1，同时采 RAM + GPIO ---" % I_URG)
        b.wp(I_URG, 1)
        t_trig = time.time()
        odrs = {}
        samples = []          # (t, [old0,old1], [pat0,pat1], pulse)
        while time.time() - t_trig < 90:
            ts = time.time() - t_trig
            old, pat = b.sample(odrs)
            samples.append((ts, old, pat, b.p(I_PULSE)))
            b.wp(I_URG, 1)    # 钉住急停（330 会把它覆盖回 0）
            if old[0] <= 0 and old[1] <= 0:
                break
        b.wp(I_URG, 0)
        say("  采 %d 拍，%.1fs，平均间隔 %.1f ms"
            % (len(samples), samples[-1][0],
               (samples[-1][0] - samples[0][0]) / max(1, len(samples) - 1) * 1000))
        say()

        pu = sorted(set(x[3] for x in samples))
        say("过程中 [802] 取值：%s" % pu)
        say()

        say("=== 对账：RAM 减量  vs  GPIO 相位跳变次数 ===")
        for k in (0, 1):
            # RAM：折叠成「每个新值首次出现的时刻」
            ram = []
            for ts, old, pat, _ in samples:
                if not ram or old[k] != ram[-1][1]:
                    ram.append((ts, old[k]))
            # GPIO：相位图案每次变化记一次
            gp = []
            for ts, old, pat, _ in samples:
                if not gp or pat[k] != gp[-1][1]:
                    gp.append((ts, pat[k]))
            r_ram, r_gp = mono_rate(ram), mono_rate([(a, b_) for a, b_ in gp])
            say("  EEV%d：" % (k + 1))
            say("    RAM  计数器变化次数 = %d   相位图案跳变次数 = %d   %s"
                % (len(ram) - 1, len(gp) - 1,
                   "**一致**" if abs((len(ram) - 1) - (len(gp) - 1)) <= max(2, (len(ram) - 1) * 0.02)
                   else "**不一致，差 %d**" % ((len(ram) - 1) - (len(gp) - 1))))
            if r_ram:
                say("    RAM  速率 = %.1f 步/秒（%d→%d，%.2fs）"
                    % (r_ram["rate"], r_ram["from"], r_ram["to"], r_ram["dt"]))
            if r_gp:
                say("    GPIO 速率 = %.1f 相位/秒" % r_gp["rate"])
            if r_ram and r_gp:
                say("    比值 GPIO/RAM = %.3f   %s"
                    % (r_gp["rate"] / r_ram["rate"],
                       "≈1 ⇒ RAM 计数器与引脚脉冲 1:1，之前测的速率是真的"
                       if abs(r_gp["rate"] / r_ram["rate"] - 1) < 0.05
                       else "≠1 ⇒ 两者不等价，之前的速率要用 GPIO 重算"))
            say()

        say("--- 复原 ---")
        for i in (0, 1):
            b.wp(ENA(i), 0); b.wp(TGT(i), 0)
        time.sleep(1.0)
        say("  [1406]=%d Manual=[%d,%d] Old=[%d,%d]"
            % (b.p(I_URG), b.p(ENA(0)), b.p(ENA(1)), b.p(OLD(0)), b.p(OLD(1))))
        if t.get_state() == t.State.HALTED:
            t.resume(); say("  !! HALTED，已 resume")
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
