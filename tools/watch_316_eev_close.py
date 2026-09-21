# -*- coding: utf-8 -*-
"""长时间盯 PSC316 外机 EEV，抓**真实关阀**曲线 + **GPIO 引脚 vs RAM 计数器**对账（只读）。

两件事一起做：

  ① 真实关阀速率 —— 真实关闭由机组自己触发（压机停 → EEV 按 §3.9 关），时机不由我定。
  ② 回答「`Parameter[809]/[810]` 到底是不是引脚实际脉冲」——
     本项目有前科：Y15/Y16 那次 RAM 在翻、引脚其实恒定（调试记录 §26/§28）。
     大忌是**拿 RAM 瞬态当引脚翻转**，所以这里同时采 GPIO ODR 直接对账。

## 引脚不写死，自动发现

`WELLTHINKER/EEV/eev.h` 里有两套并存的 API（`MT1_A_H()` 宏 与 `STEP_MOTOR_NUM()`），
而且 316 的 `Obj/eev.o` 对 **GPIOC 只用库函数** `GPIO_SetBits(GPIOC,pin)`
（反汇编里只有基址 0x40011000，没有 BSRR/BRR 偏移）⇒ **从反汇编反推不出引脚掩码**。
所以脚本采 3 个口的**全部 32 位 ODR**，关阀时**自动列出哪些位在跳** —— 让数据指出引脚。

（注意：同一口上还挂着风机/接触器等，所以可能有无关位在跳；报告里会按跳变次数排序，
  跳得最多的那几位就是电机相位。）

## 判据

    某段时间里  RAM 计数器变化次数  是否 ==  GPIO 相位跳变次数

跑法：
    python.exe tools/watch_316_eev_close.py 2400 --status=60
"""
from __future__ import annotations

import pathlib
import sys
import time

from pyocd.core.helpers import ConnectHelper

OUT = pathlib.Path(__file__).resolve().parent / "watch_316_eev_close.txt"

PB = 0x2000164A
I_PULSE, I_CTRLNUM, I_URG = 802, 804, 1406
NEW = lambda i: 805 + i          # noqa: E731
OLD = lambda i: 809 + i          # noqa: E731
N = 2

GPIO_ODR = (("B", 0x40010C0C), ("C", 0x4001100C), ("D", 0x4001140C))

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


def mono_rate(steps):
    """steps = [(t, value)]，取最长单调递减段（关阀是递减）。"""
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


def ram_seq(trace, k):
    """折叠成 [(t, value)] —— 每个新数值只留首次出现的时刻。"""
    out = []
    for row in trace:
        v = row[1][k]
        if not out or v != out[-1][1]:
            out.append((row[0], v))
    return out


def gpio_seq(trace):
    """把三个 ODR 拼成一个 96 位状态，折叠成 [(t, state)]。"""
    out = []
    for row in trace:
        st = tuple(row[3])
        if not out or st != out[-1][1]:
            out.append((row[0], st))
    return out


def toggled_bits(trace):
    """关阀期间哪些 ODR 位在跳，按跳变次数排序。"""
    n = len(GPIO_ODR)
    seen = [dict() for _ in range(n)]
    for m in range(1, len(trace)):
        a, b = trace[m - 1][3], trace[m][3]
        for p in range(n):
            d = a[p] ^ b[p]
            while d:
                bit = (d & -d).bit_length() - 1
                seen[p][bit] = seen[p].get(bit, 0) + 1
                d &= d - 1
    res = []
    for p, (name, _) in enumerate(GPIO_ODR):
        for bit, cnt in sorted(seen[p].items(), key=lambda x: -x[1]):
            res.append(("GPIO%s.%d" % (name, bit), cnt))
    return res


def main() -> int:
    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 2400.0
    status = 60.0
    for a in sys.argv[1:]:
        if a.startswith("--status="):
            status = float(a.split("=", 1)[1])

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"})
    if session is None:
        say("✗ 连不上 ST-Link"); return 1

    with session:
        t = session.target
        b = t
        say("=== 316 外机 EEV 关阀看门狗 + GPIO/RAM 对账（只读）===")
        say("内核 = %s" % t.get_state())
        if t.get_state() == t.State.HALTED:
            t.resume(); say("  已 resume")

        def p(i):
            return s16(int.from_bytes(bytes(b.read_memory_block8(PB + 2 * i, 2)), "little"))

        say("版本 = %s" % [p(1000 + k) for k in range(6)])
        say("盯 %.0f 秒，心跳每 %.0f 秒。**只读，不写任何寄存器。**" % (seconds, status))
        say("GPIO: 采 B/C/D 三个口的全部 32 位 ODR，关阀时自动列出哪些位在跳")
        say()

        t0 = time.time()
        last_status = -1e9
        trace: list = []
        capturing = False
        prev = [p(OLD(0)), p(OLD(1))]
        cap_start = 0.0
        while time.time() - t0 < seconds:
            ts = time.time() - t0
            v = [p(OLD(0)), p(OLD(1))]
            pu = p(I_PULSE)
            odr = tuple(int.from_bytes(bytes(b.read_memory_block8(a, 4)), "little")
                        for _, a in GPIO_ODR)
            trace.append((ts, v, pu, odr))
            if len(trace) > 80000:
                trace = trace[-50000:]

            dec = any(v[k] < prev[k] for k in range(N))
            if dec and not capturing:
                capturing, cap_start = True, ts
                say("[关闭开始] t=%.1fs  Old=[%d,%d]  New=[%d,%d]  [802]=%d"
                    % (ts, v[0], v[1], p(NEW(0)), p(NEW(1)), pu))
                trace = [x for x in trace if x[0] >= ts - 1.0]
            if capturing and not dec and ts - cap_start > 3.0:
                say("[关闭结束] t=%.1fs" % ts)
                for k in range(N):
                    r = mono_rate(ram_seq(trace, k))
                    if r is None:
                        say("    EEV%d：RAM 没有有效位移" % (k + 1)); continue
                    say("    EEV%d：RAM %d → %d（%d 步 / %.2fs）= **%.1f 步/秒**"
                        % (k + 1, r["from"], r["to"], r["dn"], r["dt"], r["rate"]))
                g = gpio_seq(trace)
                gsum = sum(1 for k in range(N)
                           for m in range(1, len(trace))
                           if trace[m][1][k] != trace[m - 1][1][k])
                say("    对账：RAM 变化共 %d 次 ／ GPIO 相位状态跳变 %d 次" % (gsum, len(g) - 1))
                gb = toggled_bits(trace)
                say("    关阀期间在跳的 ODR 位（按跳变次数）：%s"
                    % "  ".join("%s×%d" % (nm, c) for nm, c in gb[:10] if c > 2))
                if gsum and abs(gsum - (len(g) - 1)) <= max(4, gsum * 0.05):
                    say("    ⇒ **RAM 与 GPIO 1:1**：RAM 计数器就是引脚脉冲，之前测的速率成立")
                elif gsum:
                    say("    ⇒ **两者不等价**（差 %d）：之前的速率要用 GPIO 重算" % (gsum - (len(g) - 1)))
                pu_all = [x[2] for x in trace]
                say("    过程中 [802] 取值：%s   （读到 20 ⇒ V12.17 补偿生效）" % sorted(set(pu_all)))
                say()
                capturing = False
                trace = []

            prev = v
            if ts - last_status >= status:
                last_status = ts
                say("  t=%6.0fs  [802]=%-3d Old=[%4d,%4d] New=[%4d,%4d] CtrlNum=%-3d [1406]=%d"
                    % (ts, pu, v[0], v[1], p(NEW(0)), p(NEW(1)), p(I_CTRLNUM), p(I_URG)))
                OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
            time.sleep(0.004)

        if t.get_state() == t.State.HALTED:
            t.resume(); say("!! HALTED，已 resume")
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
