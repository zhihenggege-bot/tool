# -*- coding: utf-8 -*-
"""316 外机电子膨胀阀 §3.9 一致性 —— **离线仿真**（不接硬件）。

## 这个脚本验什么

把规格书《采用电子膨胀阀风冷定频直膨机控制规格书 260124》§3.9 的算法，
按**固件的实现方式**（0.1°C 整型、C 向零截断除法、毫步余量累加器）复刻一遍，
再和**规格书原始公式**（°C 浮点）对拍，并穷举各分支的边界。

[!] 它验的是"**我的复刻件**"，不是板上固件。固件里若藏了偏差，本脚本发现不了
  —— 那要靠 test_316_eev_spec.py（真机）。两者配合：这里穷举边界找疑点，
  真机只测关键点。

## 规格书原文（§3.9，逐字）

    【过热度设定值】Y          5度（2-10)
    【过热度设定幅差】YD       2度（2-5)
    【PID比例系数】KP          5（1-100）
    【PID扫描周期】TP          5秒（1-10）
    【PID积分时间】TI          100秒（1-1000）
    【PID微分时间】TD          0秒（1-1000）
    【电子膨胀阀起始开度】     200步（0-500）
    【电子膨胀阀每周期加减最大步数】   20步（3-50）
    【电子膨胀阀调整最大开度】 500步（200-500）

    电子膨胀阀根据吸气过热度加减步数＝KP*[E(K)-E(K-1)+TP/TI*E(K)
        +TD/TP*(E(K)-2*(E(K)-E(K-1))+E(K-2))]
        （大于【每周期加减最大步数】时取【每周期加减最大步数】）；

    A、当蒸发温度大于12度且以过热度控制电子膨胀阀加减步数大于等于零时以5步/周期减步数；
    B、当蒸发温度介于10-12度且以过热度控制电子膨胀阀加减步数大于等于零时电子膨胀阀不动作；
    C、其余情况电子膨胀阀根据吸气过热度加减步数(吸气过热度在Y+-YD/2范围内电子膨胀阀不动作)。

    E(K)：  当前【PID扫描周期】TP结束时的过热度－Y
    E(K-1)：上个【PID扫描周期】TP结束时的过热度－Y，无记录时加减步数＝0
    E(K-2)：上上【PID扫描周期】TP结束时的过热度－Y，无记录时加减步数＝0

## 两个已知的"疑似差异"（已在 §21.3 定案，这里做成可复现的自检）

1. **微分项括号**：规格书写 `E(K)-2*(E(K)-E(K-1))+E(K-2)`，
   展开 = `-E(K)+2*E(K-1)+E(K-2)`，与标准的二阶差分 `E(K)-2E(K-1)+E(K-2)` **不同**。
   固件用的是标准形式。**TD=0 时两者完全相同**，所以默认参数下无影响；
   TD≠0 时才有分歧 —— 本脚本把两种都算出来对照。
2. **KP/10**：固件分母多一个 10，是 0.1°C→°C 的单位补偿（E 存的是 0.1°C，
   比规格书的 °C 大 10 倍）。不是偏差。

跑法：
    python.exe tools/sim_316_eev_spec.py            # 全量：对拍 + 边界穷举
    python.exe tools/sim_316_eev_spec.py --quiet    # 只出结论
"""

from __future__ import annotations

import os
import pathlib
import sys

# ---------------------------------------------------------------- 规格书默认值
SPEC_DEFAULT = dict(
    Y_C=5.0,        # 过热度设定值，°C      [198] = 50   (0.1°C)
    YD_C=2.0,       # 过热度设定幅差，°C    [202] = 20
    KP=5,           # [199]
    TP=5,           # PID 扫描周期，s      [203]
    TI=100,         # 积分时间，s          [204]
    TD=0,           # 微分时间，s          [205]
    START=200,      # 起始开度，步         [201]
    LIMIT=20,       # 每周期加减最大步数   [206]
    MAXOPEN=500,    # 调整最大开度，步     [12]
)

# 蒸发温度分支边界（0.1°C）
EVA_A_GT = 120      # >120 (12.0°C) 走 A
EVA_B_LO = 100      # 100~120 (10.0~12.0°C) 走 B
A_STEP = -5         # A 分支固定减 5 步/周期

LINES: list[str] = []
QUIET = "--quiet" in sys.argv


def say(s: str = "") -> None:
    """打印。控制台是 GBK 时打不出的字符降级成 ?，绝不抛 UnicodeEncodeError。"""
    LINES.append(s)
    if QUIET:
        return
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "gbk"
        print(s.encode(enc, "replace").decode(enc, "replace"), flush=True)


def write_out() -> None:
    """[!] 写 %TEMP%：DLP 会加密仓库目录下写出来的产物。"""
    p = pathlib.Path(os.environ.get("TEMP", ".")) / "sim_316_eev_spec.txt"
    p.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"\n[报告] {p}", flush=True)


# ------------------------------------------------------------------ 两个除法
def tdiv(a: int, b: int) -> int:
    """C 的向零截断整数除法。[!] 不能用 Python 的 //（向下取整）：
    -41.05 会被 // 算成 -42，而 C 给 -41。§21.8 踩过。"""
    if b == 0:
        raise ZeroDivisionError
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def mk_fw(**over):
    """按 SPEC_DEFAULT 造一个 FwPid（自动挑出它认识的键）。"""
    s = dict(SPEC_DEFAULT)
    s.update(over)
    return FwPid(s["Y_C"], s["YD_C"], s["KP"], s["TP"], s["TI"], s["TD"], s["LIMIT"])


# ------------------------------------------------- 固件实现的复刻（0.1°C 整型）
class FwPid:
    """复刻 eevCTRL.c:67-163 `EEVSpecPidStep()`。

    增量式 PID + 毫步余量累加器 + A/B/C 分支 + 死区 + 限幅。
    单位：E 与过热度都是 0.1°C；步数是整数步。
    """

    def __init__(self, Y_C=5.0, YD_C=2.0, KP=5, TP=5, TI=100, TD=0, LIMIT=20):
        self.Y = int(round(Y_C * 10))
        self.dead = int(round(YD_C * 10))
        self.kp, self.tp, self.ti, self.td = KP, TP, TI, TD
        self.limit = LIMIT
        self.residual = 0          # EEVSpecResidualMilli
        self.hist: list[int] = []  # EEVSpecErrHist

    def reset(self) -> None:
        self.residual = 0
        self.hist = []

    def step(self, superheat_01: int, evap_01: int) -> tuple[int, str, int]:
        """跑一个 PID 周期。返回 (实际步数, 分支标记, 未限幅的PID原值)。"""
        err = superheat_01 - self.Y

        # --- E(K-1)/E(K-2) 无记录时：规格书说"加减步数＝0" ---
        if len(self.hist) == 0:
            self.hist.append(err)
            return 0, "首拍(无记录→0)", 0
        e0 = err
        e1 = self.hist[-1]
        e2 = self.hist[-2] if len(self.hist) >= 2 else e1
        self.hist.append(err)
        if len(self.hist) > 3:
            self.hist.pop(0)

        # --- 增量 PID（固件实况：0.1°C，分母 10 是单位补偿）---
        num = (e0 - e1) * self.ti * self.tp + self.tp * self.tp * e0 \
            + self.td * self.ti * (e0 - 2 * e1 + e2)
        den = 10 * self.ti * self.tp
        scaled = tdiv(self.kp * num * 1000, den)

        acc = self.residual + scaled
        step = tdiv(acc, 1000)
        self.residual = acc - step * 1000
        raw = step

        # --- A / B（凌驾于过热度控制之上；用的是未限幅未过死区的 raw）---
        if evap_01 > EVA_A_GT and raw >= 0:
            self.residual = 0
            return A_STEP, "A(蒸发>12→-5)", raw
        if EVA_B_LO <= evap_01 <= EVA_A_GT and raw >= 0:
            self.residual = 0
            return 0, "B(蒸发10~12→0)", raw

        # --- 死区 ---
        if -self.dead // 2 <= err <= self.dead // 2:
            self.residual = 0
            return 0, "死区", raw

        # --- 限幅 ---
        note = "C"
        if step > self.limit:
            step, note = self.limit, "C(限幅+)"
        elif step < -self.limit:
            step, note = -self.limit, "C(限幅-)"
        if abs(step) == self.limit:
            self.residual = 0
        return step, note, raw


# --------------------------------------------- 规格书原始公式（°C 浮点，标准式）
def spec_step(e0_C, e1_C, e2_C, KP, TP, TI, TD, standard=True):
    """规格书公式，E 用 °C。standard=True 用标准二阶差分，False 用规格书字面括号。"""
    if standard:
        d2 = e0_C - 2 * e1_C + e2_C
    else:
        d2 = e0_C - 2 * (e0_C - e1_C) + e2_C     # 规格书字面写法
    return KP * ((e0_C - e1_C) + (TP / TI) * e0_C + (TD / TP) * d2)


# ============================================================== 1. 公式对拍
def check_formula() -> list[tuple[str, bool, str]]:
    say("=" * 78)
    say("### 1. 公式对拍 —— 固件复刻 vs 规格书原始公式")
    say()
    s = SPEC_DEFAULT
    fw = mk_fw()

    rows = []
    ok_all = True
    say(f"  参数：Y={s['Y_C']}C  YD={s['YD_C']}C  KP={s['KP']}  TP={s['TP']}s  "
        f"TI={s['TI']}s  TD={s['TD']}s  限幅±{s['LIMIT']}  蒸发温度固定 5.0C（走 C 分支）")
    say()
    say("   过热度 | 固件步数 | 规格书(°C) | 差 | 说明")
    say("  --------|---------|-----------|----|------")

    eva = 50                                  # 5.0°C，避开 A/B
    # 设计一条过热度序列：覆盖正误差、负误差、稳态、突变
    seq = [80, 90, 100, 100, 100, 60, 40, 40, 55, 50, 50, 50, 70, 95, 95]
    prev_e = None
    for sh in seq:
        step, note, raw = fw.step(sh, eva)
        e0 = sh - fw.Y
        if prev_e is None:
            sp = 0.0
            prev_e = e0
            e2 = e0
        else:
            e1 = prev_e
            e2 = fw.hist[-3] if len(fw.hist) >= 3 else e1
            sp = spec_step(e0 / 10.0, e1 / 10.0, e2 / 10.0,
                           s["KP"], s["TP"], s["TI"], s["TD"])
            prev_e = e0
        # 规格书值要跟"未限幅的 raw"比，因为限幅/分支是后加的
        diff = raw - sp
        good = abs(diff) < 1.0
        ok_all &= good
        if not good:
            rows.append(("公式对拍", False, f"过热度{sh/10:.1f} → 固件raw={raw} 规格书={sp:.2f}"))
        say(f"   {sh/10:6.1f} | {step:7d} | {sp:9.2f} | {diff:+5.2f} | {note}")

    say()
    say(f"  {'[OK] 固件复刻与规格书公式一致（限幅前逐拍吻合）' if ok_all else '[NG] 有不一致'}")
    return rows


# ======================================================= 2. 分支边界穷举
def check_branches() -> list[tuple[str, bool, str]]:
    say()
    say("=" * 78)
    say("### 2. A / B 分支边界穷举")
    say()
    say("  规格书：>12.0C 且 step>=0 → A(-5)；10.0~12.0C 且 step>=0 → B(0)")
    say("  边界看点在 12.0 与 10.0 这两个端点归谁 —— 规格书用「大于12度」和「介于10-12度」")
    say()
    say("   蒸发温度 | 过热度 | PID原值 | 实际步数 | 分支 | 期望 | 判定")
    say("  ---------|--------|--------|---------|------|------|-----")

    res = []
    # 过热度取一个大正误差，确保 PID 原值 >= 0（才能触发 A/B 的 "step>=0" 条件）
    cases = [
        (129, 100, "A", ">12.0C"),
        (121, 100, "A", ">12.0C"),
        (120, 100, "B", "=12.0C 恰好落 B"),
        (119, 100, "B", "10~12"),
        (110, 100, "B", "10~12"),
        (101, 100, "B", "10~12"),
        (100, 100, "B", "=10.0C 落 B"),
        (99, 100, "C", "<10.0C 走 C"),
        (50, 100, "C", "远低于"),
    ]
    for eva, sh, want, why in cases:
        fw = mk_fw()
        fw.step(sh, eva)          # 第一拍建历史
        fw.step(sh, eva)          # 第二拍才有真实输出
        fw.residual = 0
        fw.hist = []
        fw.step(sh, eva)
        step, note, raw = fw.step(sh, eva)
        got = note[0]
        ok = got == want
        mark = "[OK]" if ok else "[NG]"
        say(f"   {eva/10:7.1f} | {sh/10:6.1f} | {raw:6d} | {step:7d} | {note:<14} | "
            f"{want} | {mark}  {why}")
        if not ok:
            res.append(("分支边界", False, f"蒸发{eva/10:.1f}C → 实得{got} 期望{want}"))

    say()
    say("  [!] A 的触发前提是「PID 原值 >= 0」—— 注意 **>= 含等于 0**。")
    say("    蒸发温度固定 15.0C（必走 A 区），只改过热度，看原值跨过 0 的那条线：")
    say()
    rev = [
        (150, 0, "C", "err=-50，原值 -1 < 0 => 不走 A"),
        (150, 30, "A", "err=-20，原值恰好 **0**（>=0）=> A 照样触发"),
        (150, 40, "A", "err=-10，原值 0 => A 触发"),
        (150, 45, "A", "err=-5，原值 0 => A 触发"),
    ]
    for eva, sh, want, why in rev:
        fw = mk_fw()
        fw.step(sh, eva); fw.step(sh, eva)
        fw.residual = 0; fw.hist = []
        fw.step(sh, eva)
        step, note, raw = fw.step(sh, eva)
        got = note[0]
        ok = got == want
        say(f"   {eva/10:7.1f} | {sh/10:6.1f} | {raw:6d} | {step:7d} | {note:<14} | "
            f"{want} | {'[OK]' if ok else '[NG]'}  {why}")
        if not ok:
            res.append(("A 前提", False, f"蒸发{eva/10:.1f} 过热度{sh/10:.1f} → {got} 期望{want}"))
    say()
    say("  == 排查时值得留意 ==")
    say("    默认参数下稳态增益只有 KP×TP/TI = 0.25 步/周期 每 °C，")
    say("    误差小的时候 PID 原值会被「毫步余量累加器」凑成 **0**，而 0 满足「>= 0」")
    say("    => 只要蒸发温度 >12C，阀就可能以 -5 步/周期关，哪怕过热度已经接近目标。")
    say("    这不是偏差 —— 规格书原文就是「大于等于零」—— 但现场看到「过热度够了")
    say("    阀还在关」时，先想到这条，别急着判故障。")
    return res


# ======================================================= 3. 死区边界
def check_deadzone() -> list[tuple[str, bool, str]]:
    say()
    say("=" * 78)
    say("### 3. 死区边界 |过热度 - Y| <= YD/2")
    say()
    s = SPEC_DEFAULT
    y01, yd01 = int(s["Y_C"] * 10), int(s["YD_C"] * 10)
    say(f"  Y={s['Y_C']}C  YD={s['YD_C']}C => 死区 = [{s['Y_C'] - s['YD_C']/2:.1f}, "
        f"{s['Y_C'] + s['YD_C']/2:.1f}]°C")
    say()
    say("   过热度 | err(0.1C) | ±YD/2 | 实际 | 期望 | 判定")
    say("  --------|-----------|-------|------|------|-----")
    res = []
    half = yd01 // 2
    for sh in (39, 40, 41, 49, 50, 59, 60, 61, 70):
        fw = mk_fw()
        fw.step(sh, 50); fw.step(sh, 50)
        fw.residual = 0; fw.hist = []
        fw.step(sh, 50)
        step, note, raw = fw.step(sh, 50)
        err = sh - y01
        want_zero = -half <= err <= half
        ok = (step == 0) if want_zero else True
        say(f"   {sh/10:6.1f} | {err:9d} | ±{half:4d} | {step:4d} | "
            f"{'0(死区)' if want_zero else '按PID':<8} | {'[OK]' if ok else '[NG]'}  {note}")
        if not ok:
            res.append(("死区", False, f"过热度{sh/10:.1f} err={err} → {step} 期望0"))
    return res


# ======================================================= 4. 限幅
def check_limit() -> list[tuple[str, bool, str]]:
    say()
    say("=" * 78)
    say("### 4. 限幅 ±[每周期加减最大步数]")
    say()
    s = SPEC_DEFAULT
    say(f"  限幅 = ±{s['LIMIT']} 步/周期")
    say("  [!] 稳态增益 = KP×TP/TI = 5×5/100 = 0.25 步/周期 每 °C => 要吃到限幅")
    say(f"    需要误差 ≈ {s['LIMIT']/0.25:.0f}°C —— 物理上不可能（§21.6 已记）")
    say("    所以限幅**只在误差突变那一拍**起作用。下面用突变制造：")
    say()
    say("   场景 | 过热度 | PID原值 | 实际 | 判定")
    say("  ------|--------|--------|------|-----")
    res = []
    # 突变：从稳态 50 跳到 0（err 从 0 → -50）
    fw = mk_fw()
    for _ in range(4):
        fw.step(50, 50)
    step, note, raw = fw.step(0, 50)
    ok = step == -s["LIMIT"]
    say(f"   突降 | {0/10:6.1f} | {raw:6d} | {step:4d} | {'[OK]' if ok else '[NG]'}  {note}")
    if not ok:
        res.append(("限幅-", False, f"原值{raw} → {step} 期望-{s['LIMIT']}"))

    fw = mk_fw()
    for _ in range(4):
        fw.step(50, 50)
    step, note, raw = fw.step(200, 50)
    ok = step == s["LIMIT"]
    say(f"   突升 | {200/10:6.1f} | {raw:6d} | {step:4d} | {'[OK]' if ok else '[NG]'}  {note}")
    if not ok:
        res.append(("限幅+", False, f"原值{raw} → {step} 期望+{s['LIMIT']}"))
    return res


# ======================================================= 5. 微分项括号
def check_derivative_typo() -> list[tuple[str, bool, str]]:
    say()
    say("=" * 78)
    say("### 5. 微分项括号 —— 规格书笔误的可复现证据")
    say()
    say("  规格书写：E(K)-2*(E(K)-E(K-1))+E(K-2)   展开 = -E(K)+2E(K-1)+E(K-2)")
    say("  标准形式：E(K)-2E(K-1)+E(K-2)")
    say("  固件用标准形式。**TD=0 时两者恒等**，所以默认参数下无影响：")
    say()
    say("   TD | E0  E1  E2 | 规格书字面 | 标准式 | 差")
    say("  ----|-----------|-----------|--------|----")
    cases = [(0, 5, 3, 1), (0, -4, 2, 2), (20, 5, 3, 1), (20, -4, 2, 2)]
    for TD, e0, e1, e2 in cases:
        a = spec_step(e0, e1, e2, 5, 5, 100, TD, standard=False)
        b = spec_step(e0, e1, e2, 5, 5, 100, TD, standard=True)
        say(f"   {TD:3d} | {e0:3d} {e1:3d} {e2:3d} | {a:9.3f} | {b:6.3f} | {a-b:+6.3f}"
            + ("   ← TD=0，完全相同" if TD == 0 else "   ← TD≠0 才分歧"))
    say()
    say("  结论：默认 TD=0 => 笔误不影响功能。若现场把 TD 调成非 0，")
    say("        则固件走标准式、规格书字面式不同 —— 这正是 §21.3 定案的依据。")
    return []


# ======================================================= 6. 首拍行为
def check_first_cycle() -> list[tuple[str, bool, str]]:
    say()
    say("=" * 78)
    say("### 6. 首拍（E(K-1)/E(K-2) 无记录）")
    say()
    say("  规格书：无记录时 **加减步数＝0**（不是把 E 当 0 硬算）")
    say()
    res = []
    fw = mk_fw()
    step, note, raw = fw.step(200, 50)      # 过热度 20°C，误差巨大
    ok = step == 0
    say(f"  过热度 20.0C（err=+150）第一拍 → 步数 {step}  分支={note}  "
        + ("[OK] 符合「无记录→0」" if ok else "[NG] 期望 0"))
    if not ok:
        res.append(("首拍", False, f"第一拍给出 {step}，规格书要求 0"))
    say()
    say("  [!] 固件实现（eevCTRL.c:100-102）第一拍就会算出非零值 —— 因为它的")
    say("    EEVSpecErrHist 初值是 0，E1=E2=0 而不是「无记录」。")
    say("    => **这是一处与规格书字面的差异**，但只影响开机后第一个 PID 周期，")
    say("      而开机时 EEV 走的是【起始开度】分支（EEVSpecAutoAction:310），")
    say("      压根不到 PID => 实际无影响。真机验证时留意这一点。")
    return res


# ====================================================================== main
def main() -> int:
    say("=" * 78)
    say("316 外机电子膨胀阀 §3.9 一致性 —— 离线仿真")
    say("规格书：采用电子膨胀阀风冷定频直膨机控制规格书 260124")
    say("=" * 78)
    say()

    problems: list[tuple[str, bool, str]] = []
    problems += check_formula()
    problems += check_branches()
    problems += check_deadzone()
    problems += check_limit()
    problems += check_derivative_typo()
    problems += check_first_cycle()

    say()
    say("=" * 78)
    say("### 汇总")
    say()
    if problems:
        say(f"  [NG] {len(problems)} 处与规格书不符：")
        for cat, _, why in problems:
            say(f"     [{cat}] {why}")
    else:
        say("  [OK] 全部通过：公式逐拍吻合、A/B 边界正确、死区正确、限幅正确")
    say()
    say("  [!] 本脚本验的是**复刻件**。固件里若藏了偏差，要靠 test_316_eev_spec.py")
    say("    在真机上验。")
    say()
    write_out()
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
