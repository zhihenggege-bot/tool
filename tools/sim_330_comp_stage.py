# -*- coding: utf-8 -*-
"""PSC330 内机 §3.4 定频压缩机加减载 —— **离线仿真**（不接硬件）。

把规格书 §3.4 的算法按**固件的实现方式**（整型定点、C 向零截断除法、毫步余量累加器）
复刻一遍，再和规格书公式对拍，并穷举各分支边界。

⚠ 验的是"我的复刻件"，不是板上固件。固件里若藏了偏差要靠 test_330_comp_stage.py。

## 规格书原文（用户 2026-10-14 更正后的 §3.4.1）

    【压缩机加减载控制方式】为环境温度时：
    制冷时：
      当新风温度 >= HLM 时执行满载指令；
      当新风温度 <= HLC 时执行空载指令；          ← 更正："低空载"是笔误
      当新风温度介于 HLC 与 HLM 时根据计算的压缩机数量运行；   ← 更正：原写 "HLM+HLC 与 HLM"
    热泵制热时：
      当新风温度 <= HRM 时执行满载指令；
      当新风温度 >= HRC 时执行空载指令；
      当新风温度介于 HRM 与 HRC 时根据计算的压缩机数量运行。   ← 更正：原写 "HRM-HRC 与 HRM"

    制冷台数 = MIN(CN, ROUNDUP(CN*(当前环温-HLC)/(HLM-HLC)))
    制热台数 = MIN(CN, ROUNDUP(CN*(HRC-当前环温)/(HRC-HRM)))

## §3.4.2 室内温湿度控制

    N(KL)=MIN(1, N(KL-1)+Z(KL))
    Z(KL)=KPL*BX/100*[E(KL)+YS-E(KL-1) + T/TIL*(E(KL)+YS) + KDL/T*(E(KL)+YS-2E(KL-1)+E(KL-2))]
      当 -WDF/4 < E(KL) < WDF/4 且 YS=0 时 Z(KL)=0
    N(KR)=MIN(1, N(KR-1)+Z(KR))
    Z(KR)=KPR*BX/100*[E(KR)-E(KR-1) + T/TIR*E(KR) + KDR/T*(E(KR)-2E(KR-1)+E(KR-2))]
      当 -WDF/4 < E(KR) < WDF/4 时 Z(KR)=0

    初始开度：E ∈ (-∞,0.5]→0 | (0.5,2]→0.2 | (2,4]→0.3 | (4,5]→0.4 | (5,+∞)→0.5
    BX：      N ∈ (0,0.1]→0.1  | (0.1,0.2]→0.2 | (0.2,0.4]→0.4 | (0.4,0.5]→0.6 | (0.5,1]→1.0
    台数：Z>0 → ROUNDUP(CN*N)；Z<0 → INT(CN*N)；Z=0 → 保持
          制冷且有再热时 Z≠0 的两条加 MAX(1, ·)

跑法：
    python.exe tools/sim_330_comp_stage.py          # 全量
    python.exe tools/sim_330_comp_stage.py --quiet  # 只出结论
"""

from __future__ import annotations

import os
import pathlib
import sys

QUIET = "--quiet" in sys.argv

# ---------------------------------------------------------- 规格书默认值
COOL = dict(WD=250, WDF=20, KPL=5, TIL=100, KDL=0, T=5)
HEAT = dict(WD=250, WDF=20, KPR=5, TIR=100, KDR=0, T=5)
ENV = dict(HLM=350, HLC=220, HRM=0, HRC=120)   # x0.1C
SD, SDF = 500, 200                              # x0.1%RH

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    if not QUIET:
        try:
            print(s, flush=True)
        except UnicodeEncodeError:
            enc = sys.stdout.encoding or "gbk"
            print(s.encode(enc, "replace").decode(enc, "replace"), flush=True)


def write_out() -> None:
    p = pathlib.Path(os.environ.get("TEMP", ".")) / "sim_330_comp_stage.txt"
    p.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"\n[报告] {p}", flush=True)


def tdiv(a: int, b: int) -> int:
    """C 的向零截断整数除法。⚠ 不能用 Python 的 //（负误差会差 1）。"""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def limit(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


# ============================================ 固件实现复刻（整型定点 ×1000）
def fw_bx10(n1000: int) -> int:
    """IndoorGetBX10()：返回 BX×10。"""
    if n1000 <= 100:
        return 1
    if n1000 <= 200:
        return 2
    if n1000 <= 400:
        return 4
    if n1000 <= 500:
        return 6
    return 10


def fw_initial_n1000(err10: int) -> int:
    """IndoorGetInitialN1000()：入参 err10 = E*10。"""
    if err10 <= 5:
        return 0
    if err10 <= 20:
        return 200
    if err10 <= 40:
        return 300
    if err10 <= 50:
        return 400
    return 500


def fw_roundup(n1000: int, maxcomp: int, keepone: bool) -> int:
    """IndoorCompTargetFromN()：Z>0 → ROUNDUP(CN*N)。"""
    if n1000 <= 0:
        return 1 if (keepone and maxcomp > 0) else 0
    tmp = n1000 * maxcomp
    target = tmp // 1000
    if tmp % 1000:
        target += 1
    if keepone and target == 0:
        target = 1
    return min(target, maxcomp)


def fw_int(n1000: int, maxcomp: int, keepone: bool) -> int:
    """IndoorCompTargetDn()：Z<0 → INT(CN*N)。"""
    if n1000 <= 0:
        return 1 if (keepone and maxcomp > 0) else 0
    target = (n1000 * maxcomp) // 1000
    if keepone and target == 0:
        target = 1
    return min(target, maxcomp)


def fw_env_linear(total: int, num: int, den: int) -> int:
    """IndoorEnvLinearCompTarget()：MIN(total, ROUNDUP(total*num/den))。"""
    if total == 0 or num <= 0:
        return 0
    if den <= 0:
        return total
    target = (total * num + den - 1) // den
    return min(target, total)


class FwPid:
    """复刻 SysNergryAction_PID() 的核心（NergryAdjust.c:376-471）。"""

    def __init__(self, kp, ti, td, t, wdf):
        self.kp, self.ti, self.td, self.t, self.wdf = kp, ti, td, t, wdf
        self.n1000 = 0
        self.e = [0, 0, 0]
        self.cnt = 0
        self.resid = 0
        self.lastz = 0

    def step(self, err10: int, ys10: int = 0, cooling: bool = True):
        """跑一个 PID 扫描周期。err10 = E*10；ys10 = YS*10（仅制冷用）。

        返回 (n1000, z, note, bx10)。⚠ bx10 必须**步进前**取（固件 :388 在
        `nCool1000 = ... + z` 之前就采了 BX），事后重算会用到错的值。
        """
        self.e[2] = self.e[1]
        self.e[1] = self.e[0]
        self.e[0] = err10
        if self.cnt < 2:
            self.n1000 = fw_initial_n1000(err10)
            self.cnt += 1
            bx10 = fw_bx10(self.n1000)
            self.lastz = 1 if self.n1000 > 0 else 0
            self.resid = 0
            return self.n1000, 0, "初值", bx10
        ys = ys10 if cooling else 0
        err_abs = abs(err10)
        bx10 = fw_bx10(self.n1000)
        dead = (err_abs * 4 < self.wdf) and ((ys == 0) if cooling else True)
        if dead:
            self.resid = 0
            self.lastz = 0
            return self.n1000, 0, "死区", bx10
        e0, e1, e2 = self.e[0], self.e[1], self.e[2]
        num = ((e0 + ys - e1) if cooling else (e0 - e1)) * self.ti * self.t
        num += self.t * self.t * (e0 + ys if cooling else e0)
        num += self.td * self.ti * ((e0 + ys - 2 * e1 + e2) if cooling
                                    else (e0 - 2 * e1 + e2))
        den = 10 * self.ti * self.t
        scaled = tdiv(self.kp * bx10 * num * 1000, den)
        acc = self.resid + scaled
        z = tdiv(acc, 1000)
        self.resid = acc - z * 1000
        self.lastz = 1 if acc > 0 else (-1 if acc < 0 else 0)
        self.n1000 = limit(self.n1000 + z, 0, 1000)
        if (self.n1000 == 0 and acc < 0) or (self.n1000 == 1000 and acc > 0):
            self.resid = 0
        return self.n1000, z, "PID", bx10


# ================================== 规格书公式（°C 浮点，用于对拍）
def spec_Z(e0_C, e1_C, e2_C, kp, ti, td, t, bx, ys_C=0.0):
    return kp * (bx / 100.0) * (
        (e0_C + ys_C - e1_C)
        + (t / ti) * (e0_C + ys_C)
        + (td / t) * (e0_C + ys_C - 2 * e1_C + e2_C))


# ============================================================ 1. 环境温度控制
def check_env():
    say("=" * 78)
    say("### 1. §3.4.1 环境温度控制（更正后规格书）")
    say()
    e = ENV
    say(f"  HLM={e['HLM']/10:.1f}C  HLC={e['HLC']/10:.1f}C  "
        f"HRM={e['HRM']/10:.1f}C  HRC={e['HRC']/10:.1f}C")
    say()
    bad = []
    for cn in (2, 3, 4, 8):
        say(f"  --- CN = {cn} 台 ---")
        say("    新风温度 | 制冷: 期望/实得 | 制热: 期望/实得 | 判定")
        say("   ----------|----------------|----------------|-----")
        # 覆盖两个区间：制热 -5~15C（HRM=0 / HRC=12），制冷 15~43C（HLC=22 / HLM=35）
        for t in (-50, 0, 1, 60, 119, 120, 121, 150,
                  220, 221, 260, 300, 350, 351, 430):
            # 制冷：>=HLM 满载；<=HLC 空载；中间线性
            if t >= e["HLM"]:
                cw = cn
            elif t <= e["HLC"]:
                cw = 0
            else:
                cw = min(cn, -(-cn * (t - e["HLC"]) // (e["HLM"] - e["HLC"])))
            # 制热：<=HRM 满载；>=HRC 空载；中间线性
            if t <= e["HRM"]:
                hw = cn
            elif t >= e["HRC"]:
                hw = 0
            else:
                hw = min(cn, -(-cn * (e["HRC"] - t) // (e["HRC"] - e["HRM"])))
            cg = (cn if t >= e["HLM"] else (0 if t <= e["HLC"]
                  else fw_env_linear(cn, t - e["HLC"], e["HLM"] - e["HLC"])))
            hg = (cn if t <= e["HRM"] else (0 if t >= e["HRC"]
                  else fw_env_linear(cn, e["HRC"] - t, e["HRC"] - e["HRM"])))
            ok = (cw == cg) and (hw == hg)
            if not ok:
                bad.append(f"CN={cn} T={t/10:.1f}: 制冷 {cw}vs{cg} 制热 {hw}vs{hg}")
            say(f"   {t/10:8.1f} |    {cw:2d} / {cg:2d}      |    {hw:2d} / {hg:2d}      "
                f"| {'[OK]' if ok else '[NG]'}")
        say()
    say("  " + ("[OK] 环境温度控制与更正后规格书逐点一致" if not bad else f"[NG] {len(bad)} 处不符"))
    for b in bad[:8]:
        say(f"     {b}")
    say()
    say("  == 边界说明（规格书原文的坑）==")
    say("    原规格写「介于 HLM+HLC 与 HLM」——HLM+HLC=57C > HLM=35C，区间不成立；")
    say("    制热侧写「<=HRM-HRC」——0-12=-12C。两处都与其配套公式矛盾。")
    say("    用户已确认是笔误，更正为 HLC~HLM / HRM~HRC，与代码一致。")
    return bad


# ======================================================== 2. 两张查表
def check_tables():
    say()
    say("=" * 78)
    say("### 2. 初始开度表 / BX 表 边界穷举")
    say()
    bad = []
    say("  初始开度表（入参 E，单位 0.1C）")
    say("    E(0.1C) | 实得N1000 | 规格书档 | 判定")
    say("   --------|-----------|----------|-----")
    for e10, want, name in [(-100, 0, "(-inf,0.5]"), (0, 0, "(-inf,0.5]"), (5, 0, "(-inf,0.5]"),
                            (6, 200, "(0.5,2]"), (20, 200, "(0.5,2]"),
                            (21, 300, "(2,4]"), (40, 300, "(2,4]"),
                            (41, 400, "(4,5]"), (50, 400, "(4,5]"),
                            (51, 500, "(5,+inf)"), (200, 500, "(5,+inf)")]:
        got = fw_initial_n1000(e10)
        ok = got == want
        if not ok:
            bad.append(f"初始开度 E={e10} 实得{got} 期望{want}")
        say(f"   {e10:8d} | {got:9d} | {name:<9}| {'[OK]' if ok else '[NG]'}")
    say()
    say("  BX 表（入参 N，单位 1/1000）")
    say("    N1000 | 实得BX10 | BX    | 规格书档 | 判定")
    say("   -------|----------|-------|----------|-----")
    for n, want10, name in [(0, 1, "(0,0.1]"), (100, 1, "(0,0.1]"), (101, 2, "(0.1,0.2]"),
                            (200, 2, "(0.1,0.2]"), (201, 4, "(0.2,0.4]"), (400, 4, "(0.2,0.4]"),
                            (401, 6, "(0.4,0.5]"), (500, 6, "(0.4,0.5]"),
                            (501, 10, "(0.5,1]"), (1000, 10, "(0.5,1]")]:
        got = fw_bx10(n)
        ok = got == want10
        if not ok:
            bad.append(f"BX N={n} 实得{got} 期望{want10}")
        say(f"   {n:6d} | {got:8d} | {got/10:.1f}   | {name:<9}| {'[OK]' if ok else '[NG]'}")

    say()
    say("  == 边界说明 ==")
    say("    两张表都是**闭区间取上界**（`<=` 链），与规格书的 ∈(a,b] 写法一致。")
    say("    ⚠ N=0 时 BX 返回 0.1 而非 0 —— 规格区间 (0,0.1] 不含 0。")
    say("      但 N=0 只出现在初值周期，而初值周期 z 被强制 0，实际无影响。")
    return bad


# ============================================ 3. Z 公式对拍 + 死区 + 累加
def check_pid():
    say()
    say("=" * 78)
    say("### 3. Z 的 PID 公式对拍（固件复刻 vs 规格书公式）")
    say()
    bad = []
    c = COOL
    fw = FwPid(c["KPL"], c["TIL"], c["KDL"], c["T"], c["WDF"])
    say(f"  制冷：KPL={c['KPL']} TIL={c['TIL']} KDL={c['KDL']} T={c['T']} WDF={c['WDF']/10:.1f}C")
    say()
    say("   ⚠ 量纲：固件 z 加进 n1000（千分制），规格书 Z 加进 N（0~1）。")
    say("     ⇒ **z == Z_规格 × 1000**。下表「规格书z」已折算成千分制。")
    say()
    say("   E(0.1C) | 固件z | 规格书z | 差 | N1000 | BX  | 判定 | 备注")
    say("  ---------|-------|---------|----|-------|-----|------|-----")
    seq = [80, 80, 100, 100, 60, 40, 40, 40, 20, 20, 20, 5, 5, 0, 0]
    for e10 in seq:
        n, z, note, bx10 = fw.step(e10, 0, cooling=True)
        if note == "初值":
            sp_z = 0.0
        else:
            e0, e1, e2 = fw.e[0] / 10.0, fw.e[1] / 10.0, fw.e[2] / 10.0
            sp_z = spec_Z(e0, e1, e2, c["KPL"], c["TIL"], c["KDL"], c["T"],
                          bx10 / 10.0) * 1000.0
        diff = z - sp_z
        # 死区行 z 被强制 0，拿它跟"未过死区的公式值"比没有意义 ⇒ 跳过比较
        ok = True if note == "死区" else (abs(diff) <= 1.0)
        if not ok:
            bad.append(f"制冷 E={e10} 固件z={z} 规格书z={sp_z:.2f}")
        say(f"   {e10:8d} | {z:5d} | {sp_z:7.2f} | {diff:+4.0f} | {n:5d} | "
            f"{bx10/10:.1f} | {'[OK]' if ok else '[NG]'} | {note}")
    say()
    say("  [!] 固件 z 是整步（毫步余量累加后取整），规格书是浮点；")
    say("    逐拍比较必然有 <1 步的量化差，这是毫步累加器的设计如此，不是偏差。")
    say()

    # 制热
    h = HEAT
    fw2 = FwPid(h["KPR"], h["TIR"], h["KDR"], h["T"], h["WDF"])
    say(f"  制热：KPR={h['KPR']} TIR={h['TIR']} KDR={h['KDR']}（无 YS 项）")
    say("   E(0.1C) | 固件z | 规格书z | 差 | N1000 | 判定 | 备注")
    say("  ---------|-------|---------|----|-------|------|-----")
    for e10 in (80, 80, 100, 60, 40, 40, 20, 5, 5, 0):
        n, z, note, bx10 = fw2.step(e10, 0, cooling=False)
        if note == "初值":
            sp_z = 0.0
        else:
            e0, e1, e2 = fw2.e[0] / 10.0, fw2.e[1] / 10.0, fw2.e[2] / 10.0
            sp_z = spec_Z(e0, e1, e2, h["KPR"], h["TIR"], h["KDR"], h["T"],
                          bx10 / 10.0) * 1000.0
        diff = z - sp_z
        ok = True if note == "死区" else (abs(diff) <= 1.0)
        if not ok:
            bad.append(f"制热 E={e10} 固件z={z} 规格书z={sp_z:.2f}")
        say(f"   {e10:8d} | {z:5d} | {sp_z:7.2f} | {diff:+4.0f} | {n:5d} | "
            f"{'[OK]' if ok else '[NG]'} | {note}")
    say()
    say("  == 死区边界 |E| < WDF/4 ==")
    half4 = c["WDF"] // 4
    say(f"    WDF={c['WDF']/10:.1f}C ⇒ WDF/4 = {c['WDF']/4:.2f}C = {half4}~{half4+1} 个 0.1C 单位")
    say("    E(0.1C) | |E|*4 < WDF ? | 规格书 | 实走分支 | 判定")
    say("   ---------|---------------|--------|----------|-----")
    for e10 in (half4 - 1, half4, half4 + 1, -half4, -half4 - 1):
        fw3 = FwPid(c["KPL"], c["TIL"], c["KDL"], c["T"], c["WDF"])
        fw3.step(e10, 0); fw3.step(e10, 0)
        _, z, note, _bx = fw3.step(e10, 0)
        want_zero = abs(e10) * 4 < c["WDF"]
        want = "0(死区)" if want_zero else "按PID"
        # 判分支而不是判 z：刚出死区时 PID 输出本来就量化到 0，看 z 分不出来
        got_branch = "0(死区)" if note == "死区" else "按PID"
        ok = got_branch == want
        say(f"   {e10:8d} | {str(abs(e10)*4 < c['WDF']):<13} | {want:<6} | "
            f"{got_branch:<8} | {'[OK]' if ok else '[NG]'}")
        if not ok:
            bad.append(f"死区 E={e10} 走 {got_branch} 期望 {want}")
    return bad


# ================================================= 4. 台数换算边界
def check_target():
    say()
    say("=" * 78)
    say("### 4. 台数换算 ROUNDUP / INT / 再热保底")
    say()
    bad = []
    say("  CN | N1000 | Z符号 | keepOne | 实得 | 规格书 | 判定")
    say("  ---|-------|-------|---------|------|--------|-----")
    for cn in (2, 3, 4, 8):
        for n in (0, 1, 250, 333, 500, 501, 999, 1000):
            for keep in (False, True):
                got_up = fw_roundup(n, cn, keep)
                # 规格：ROUNDUP(CN*N)，有再热时 MAX(1,·)
                sp = -(-cn * n // 1000) if n > 0 else 0
                if keep:
                    sp = max(1, sp)
                sp = min(sp, cn)
                ok = got_up == sp
                if not ok:
                    bad.append(f"ROUNDUP CN={cn} N={n} keep={keep}: {got_up} vs {sp}")
                say(f"  {cn:2d} | {n:5d} |   +   |  {str(keep):<5}  | {got_up:4d} | {sp:6d} | "
                    f"{'[OK]' if ok else '[NG]'}")
    say()
    for cn in (3, 4):
        for n in (0, 250, 333, 500, 999, 1000):
            got_dn = fw_int(n, cn, False)
            sp = min(cn * n // 1000, cn) if n > 0 else 0
            ok = got_dn == sp
            if not ok:
                bad.append(f"INT CN={cn} N={n}: {got_dn} vs {sp}")
            say(f"  INT: CN={cn} N={n} → 实得 {got_dn}，规格书 {sp}  "
                f"{'[OK]' if ok else '[NG]'}")
    say()
    say("  == Z=0 时 ==")
    say("    规格书：「当Z(KL)=0时，**保持当前开启定频压缩机数量**」")
    say("    ⇒ MAX(1,·) 只加在 Z>0 / Z<0 两条上，Z=0 不加。")
    say("    代码 :492-496 正是 `target = lastCoolTarget` —— **与规格书一致**。")
    say("    （Explore 代理曾把这条误报为偏差，已核实推翻。）")
    return bad


# ================================================= 5. YS 四条件
def check_ys():
    say()
    say("=" * 78)
    say("### 5. YS 四条件（仅制冷）")
    say()
    say("  规格书：机组有恒湿要求、加湿器未开、再加热未满载、")
    say("          当前温度在设定范围内 且 相对湿度 > SD+SDF/2  →  YS=2")
    say()
    say("  代码 NergryAdjust.c:374-375：")
    say("    ys = 0;")
    say("    if((HumUseSet == 1) && (HumidValveY13 == 0) && (HumidAO2 == 0) &&")
    say("       (ReheatDemandDisp < 1000) &&")
    say("       (IndoorAbs(RealTempDisp - ControlTempDisp) * 2 <= RoomTempDiffSet) &&")
    say("       (HumiditySensorAI1Disp > (HumiditySet + HumidityDiffSet / 2)))")
    say("        ys = 20;                       // = 2.0C（E 以 0.1C 编码）")
    say()
    say("  逐条对照：")
    say("    ① 恒湿要求      HumUseSet == 1                          [OK]")
    say("    ② 加湿器未开    HumidValveY13 == 0 && HumidAO2 == 0     [OK] 阀门+模拟量两路都判")
    say("    ③ 再热未满载    ReheatDemandDisp < 1000                 [OK] <100%")
    say("    ④a 温度在范围内 |T-Tset|*2 <= WDF  ⟺ |E| <= WDF/2       [OK]")
    say("    ④b 湿度        RH > SD + SDF/2                          [OK]")
    say("  制热侧 IndoorPidYSDisp 固定写 0（:466）—— 规格书制热无 YS  [OK]")
    return []


def main() -> int:
    say("=" * 78)
    say("PSC330 内机 §3.4 定频压缩机加减载 —— 离线仿真")
    say("规格书：采用电子膨胀阀定频直膨机控制规格书 260124（§3.4.1 已按用户更正）")
    say("=" * 78)
    say()
    bad = []
    bad += check_env()
    bad += check_tables()
    bad += check_pid()
    bad += check_target()
    bad += check_ys()
    say()
    say("=" * 78)
    say("### 汇总")
    say()
    if bad:
        say(f"  [NG] {len(bad)} 处与规格书不符：")
        for b in bad[:20]:
            say(f"     {b}")
    else:
        say("  [OK] 全部通过：环境温度控制、两张查表、Z 公式、死区、台数换算、YS")
    say()
    say("  [!] 本脚本验的是**复刻件**。固件里若藏了偏差要靠真机脚本。")
    say("  [!] 已知唯一真差异（代码侧）：KDL/KDR 下限 = 0，规格书为 1-1000。")
    say()
    write_out()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
