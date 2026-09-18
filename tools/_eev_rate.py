"""从 probe_330_eev.txt 里算电子膨胀阀的**开关速率**，并出可存档的证据表。

规格书（用户 2026-09-18 提供）：
    电子膨胀阀关闭时，以 **20 步/秒** 速度关闭；关闭步数 = **当前步数 + 20**

代码（`eevCTRL.c:171-202 EEVCloseStepTarget()`）：
    closeStepPerSecond = 20
    extraStep = (EMERGENCY) ? 10 : 20  ->  target = current + extraStep
    每 uc1s:  target <= 20 ? target = 0 : target -= 20

只做离线分析，不碰硬件。
"""
from __future__ import annotations

import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "probe_330_eev.txt"
OUT = HERE / "probe_330_eev_rate.txt"

LINE = re.compile(r"^\s*([\d.]+)\s+\[([^\]]*)\]\s+\[([^\]]*)\]\s*(.*)$")
PAIR = re.compile(r"EEV(\d)\s+(-?\d+)/(-?\d+)")

series: dict[int, list[tuple[float, int, int]]] = {}
comp: list[tuple[float, str, str]] = []

for raw in SRC.read_text(encoding="utf-8").splitlines():
    m = LINE.match(raw)
    if not m:
        continue
    t = float(m.group(1))
    comp.append((t, m.group(2), m.group(3)))
    for e, tgt, act in PAIR.findall(m.group(4)):
        series.setdefault(int(e), []).append((t, int(tgt), int(act)))

L: list[str] = []


def say(s: str = "") -> None:
    L.append(s)
    print(s, flush=True)


say("=== 原始日志：%s ===" % SRC.name)
say()
say("--- 330 侧压缩机状态变化 ---")
prev = None
for t, a, b in comp:
    if (a, b) != prev:
        say(f"  t={t:7.1f}  外机1={a:<16} 外机2={b}")
        prev = (a, b)

say()
say("=== 抬升段（化霜开始 -> 室内 EEV 开到【化霜时电子膨胀阀开度】）===")
for e in sorted(series):
    s = series[e]
    t_up = next((t for t, tg, _ in s if tg > 0), None)
    if t_up is None:
        continue
    goal = max(tg for _, tg, _ in s)
    t_land = next((t for t, tg, ac in s if tg > 0 and ac >= tg), None)
    if t_land is None:
        say(f"  EEV{e}: 抬起 t={t_up:.1f}  目标={goal}  **未到位**")
        continue
    d = t_land - t_up
    say(f"  EEV{e}: t={t_up:7.1f} -> {t_land:7.1f}  ({d:5.1f}s)  0 -> {goal}"
        f"   = **{goal / d:.1f} 步/秒**")

say()
say("=== 关闭段（化霜结束 -> 目标先 +20，再按 20 步/秒 降到 0）===")
say()
say("  规格书「关闭步数 = 当前步数 + 20」的判据 = 目标在关闭**第一拍先 +20**")
say()
for e in sorted(series):
    s = series[e]
    if not any(tg > 0 for _, tg, _ in s):
        continue
    # 关闭的起点：目标**向上跳**的那一拍（唯一一次升高 = 关闭指令的过冲）
    #   ⚠ 不能用 max(target) 当基准 —— max 本身就是过冲后的值。
    i0 = next((i for i in range(1, len(s)) if s[i][1] > s[i - 1][1]), None)
    if i0 is None:
        say(f"  EEV{e}: **目标全程没升高过 -> 没找到关闭过冲那一拍**")
        continue
    t0, tg0 = s[i0][0], s[i0][1]
    base = s[i0 - 1][1]
    bump = tg0 - base
    # 逐「拍」= 目标值发生变化的那一拍（不是逐采样点）
    #   ⚠ Δt 必须相对**上一拍**算，不能相对上一采样点（采样是 10Hz，会得出 0.1s 的假间隔）
    ticks: list[tuple[float, int, float]] = []
    for i in range(i0, len(s)):
        if i == i0 or s[i][1] != s[i - 1][1]:
            dt = 0.0 if not ticks else s[i][0] - ticks[-1][0]
            ticks.append((s[i][0], s[i][1], dt))
    # 实际归零：最后一个 actual>0 的采样点
    last = next((i for i in range(len(s) - 1, -1, -1) if s[i][2] > 0), None)
    t_end, a_end = (s[last][0], s[last][2]) if last is not None else (None, None)
    d = (t_end - t0) if t_end else 0.0
    say(f"  --- EEV{e} ---")
    say(f"    关闭第一拍 t={t0:.1f}  目标 {base} -> {tg0}   **Δ=+{bump}**"
        f"   {'✅ 符合「当前+20」' if bump == 20 else '⚠ 不是 +20'}")
    say("    逐拍:")
    for i, (t, tg, dt) in enumerate(ticks):
        d_prev = "" if i == 0 else "  Δ=%+d" % (tg - ticks[i - 1][1])
        say(f"      t={t:7.1f}  目标={tg:4d}{d_prev:<8}  Δt={dt:.2f}s")
    if d > 0:
        say(f"    实际: 最后一拍 t={t_end:.1f} 实际={a_end}"
            f"  -> 全程 {tg0} 步 / {d:.2f}s = **{tg0 / d:.1f} 步/秒**")
    # 逐拍间隔统计（排除第一拍 0.60s 的瞬跳）
    gaps = [dt for _, _, dt in ticks[2:]]
    if gaps:
        say(f"    步间间隔: {min(gaps):.2f} ~ {max(gaps):.2f} s"
            f"  (均 {sum(gaps) / len(gaps):.2f}s, n={len(gaps)})")

say()
say("=== 制热期间室内 EEV 是否关闭（规格：热泵制热时室内机 EEV 关闭）===")
say()
say("  探针只打印 目标或实际 非 0 的行 -> **某路 EEV 没出现在某时刻，就等于它当时是 0/0**")
for e in sorted(series):
    s = series[e]
    say(f"  EEV{e}: 首次非零 t={s[0][0]:.1f}s   => 在此之前（0 ~ {s[0][0]:.1f}s）全程 0/0")
say()
say("  ⚠ 但本段日志的起点也不是上电 —— 只能说「观测窗内、化霜之前」是关的。")

OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n-> 已写入", OUT)
