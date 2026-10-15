# -*- coding: utf-8 -*-
"""316 外机电子膨胀阀 §3.9 一致性 —— **真机测试**（一次性排查用）。

配套 sim_316_eev_spec.py（离线仿真）。本脚本在**板上真跑的固件**上验。

## 怎么造工况

过热度 = 吸气温度 − 蒸发温度。两个量各有一条可注入的通道：

    过热度  <- 吸气温度 NTC[5]  330[2534 + (u-1)*16 + 5]       1 单位 = 0.1C，1:1 线性
    蒸发温度<- 低压 AiCfgOffset(2)  330[2680 + (u-1)*49 + 2*12 + 8]  (u=1 时 [2712])
               -> 316[334] -> AI[2] -> Filter_A[0] -> R22 饱和温度表 -> CompEva1Disp

⚠ 第二条是**非线性**的（经饱和温度表、且 Filter_A 是 8 拍平均），所以脚本先做
  一次标定量出斜率，再逐点反算偏移。§21.5 记录过这条通道，本脚本实测复验。

⚠ **不能用 `UserAxValueSet`（316[499]）** 去改蒸发温度 —— §21.6 踩过，
  那条路被固件周期覆盖。用 AI 配置块的 AiCfgOffset。

## 判定

读固件**自己**的 `EEVSpecErrHist[0][0..2]`（E(K)/E(K-1)/E(K-2)）和 `NewAddValue`，
在 PC 侧按规格书公式重算，与固件实际走出来的步数比 —— 验的是实现，不是纸面。

    step = KP*[E0-E1 + TP/TI*E0 + TD/TP*(E0-2E1+E2)]  (E 单位 0.1C，分母多除一个 10)
    A: 蒸发>12.0C 且 step>=0 -> -5
    B: 蒸发 10.0~12.0C 且 step>=0 -> 0
    C: 其余；|过热度-Y| <= YD/2 不动作；限幅 +-[每周期加减最大步数]

## 重要前提

外机**必须在制热运行、压机在转**（`EEVSpecAutoAction` 的门禁：
`UserWorkModeSet==1 && running && !defrost`）。不满足就拒绝跑。

## 耗时

一次网关写 8~15 秒。默认 9 个测点 ≈ 20 次写 ≈ 5~10 分钟。

跑法：
    python.exe tools/test_316_eev_spec.py                 # 全量
    python.exe tools/test_316_eev_spec.py --list          # 只列测点不跑
    python.exe tools/test_316_eev_spec.py --only A,B      # 只跑指定分组
    python.exe tools/test_316_eev_spec.py --restore       # 只还原注入
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1
UNIT = 1

# ---- 316 RAM（fromelf -s 自 PSC316RK-V12-20250327.axf）----
PARAM_BASE = 0x2000164A
A_AI = 0x20001172           # int16 AI[14]，AI[11] = 吸气温度1
A_ERRHIST = 0x20002778      # int32 EEVSpecErrHist[2][3]
A_RESID = 0x20002790        # int64 EEVSpecResidualMilli[2]
# ⚠ 下面这几个地址以**当前** OBJ/PSC316RK-V12-20250327.axf 的 fromelf -s 为准。
#   §21.9 调试记录里那张表在这一片偏了 4 字节（Comp 记 0x20000DD4 实为 0x20000DD8、
#   Filter_A 记 0x20000DE6 实为 0x20000DEA），照抄会读到隔壁变量、静默读成 0。
A_COMP = 0x20000DD8         # uint8 Comp[5]
A_FILTERA = 0x20000DEA      # int16 Filter_A[4]，[0] = 低压1 的 kPa（蒸发温度的输入）

# ---- 316 Parameter 下标 ----
P_WMODE, P_Y, P_KP, P_PIDEN = 1, 198, 199, 200
P_START, P_YD, P_TP, P_TI, P_TD, P_LIMIT = 201, 202, 203, 204, 205, 206
P_MAXOPEN, P_DEFOPEN = 12, 21
P_REFRIG = 39               # RefrigerantSetP02
P_EVA1 = 500 + 27           # CompEva1Disp
P_OVER1 = 1437              # MainOverHeat1Disp
P_NEW, P_OLD, P_RUN = 805, 809, 813
# ★ 固件自己的 PID 诊断出口（eevCTRL.c:27 EEVSpecPublishDiag）：
#   EEV1PidErrorDisp = PLCREADPara+77 = 1497  E(K) x0.1C
#   EEV1PidStepDisp  = PLCREADPara+78 = 1498  **固件算出的步数/周期** ← 直接对拍用这个
P_E1ERR, P_E1STEP = 1420 + 77, 1420 + 78
P_E2ERR, P_E2STEP = 1420 + 79, 1420 + 80

# ---- 330 注入地址 ----
NTC5_OFF = 2534 + (UNIT - 1) * 16 + 5
EVA_OFF = 2680 + (UNIT - 1) * 49 + 2 * 12 + 8

WM = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排风", 5: "自动"}

# ---- 规格书 §3.9 默认值（用来判"参数是不是规格值"）----
SPEC = dict(Y=50, YD=20, KP=5, TP=5, TI=100, TD=0, START=200, LIMIT=20, MAXOPEN=500)

# ---- 测点：(组, 目标蒸发温度 x0.1C, 目标过热度 x0.1C, 期望分支, 说明) ----
POINTS = [
    ("A", 130, 100, "A", "蒸发13.0C 在 A 区，原值>0 => 固定 -5"),
    ("B", 121, 100, "A", "蒸发12.1C 刚过 12.0 线"),
    ("B", 120, 100, "B", "蒸发12.0C **恰好**落 B（规格书「大于12度」）"),
    ("B", 110, 100, "B", "蒸发11.0C 在 B 区中段"),
    ("B", 100, 100, "B", "蒸发10.0C **恰好**落 B（规格书「介于10-12度」）"),
    ("C", 99, 100, "C", "蒸发9.9C 刚跌破 10.0 => 走 C"),
    ("C", 50, 50, "dead", "过热度=Y=5.0C => 死区，不动作"),
    ("C", 50, 60, "dead", "过热度6.0C = Y+YD/2 **边界** => 死区"),
    ("C", 50, 61, "C", "过热度6.1C 刚出死区 => 按 PID"),
    ("C", 50, 20, "C", "过热度2.0C 远低于 Y => PID 负步"),
]

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "gbk"
        print(s.encode(enc, "replace").decode(enc, "replace"), flush=True)


def write_out() -> None:
    """⚠ 写 %TEMP%：DLP 会加密仓库目录下写出来的产物。"""
    p = pathlib.Path(os.environ.get("TEMP", ".")) / "test_316_eev_spec.txt"
    p.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"\n[报告] {p}", flush=True)


def tdiv(a: int, b: int) -> int:
    """C 的向零截断除法。⚠ 不能用 Python //（负误差会差 1，§21.8）。"""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def spec_scaled(e0: int, e1: int, e2: int, kp, tp, ti, td) -> int:
    """按固件算法算**毫步**输出（未经余量累加），这才是可比的量。

    ⚠ 不要拿 resid + scaled 去反推 step：固件会写
        acc = resid_前 + scaled;  step = acc/1000;  resid_后 = acc - step*1000
      本脚本只能读到 **resid_后**，再拿它去加 scaled 等于把减掉的 1000 又加回来，
      结果能差好几步（实测 resid=400/scaled=-3250 真值 -2，这么算得 -4）。
      正确判据是：固件步数 ∈ { tdiv(scaled,1000), 其 ±1 }（余量绝对值恒 < 1000）。
    """
    num = (e0 - e1) * ti * tp + tp * tp * e0 + td * ti * (e0 - 2 * e1 + e2)
    den = 10 * ti * tp
    return tdiv(kp * num * 1000, den)


def judge(step_raw: int, eva: int, err: int, limit: int, dead: int) -> tuple[int, str]:
    """把 PID 原值经 A/B/C/死区/限幅，返回 (期望步数, 分支)。"""
    if eva > 120 and step_raw >= 0:
        return -5, "A"
    if 100 <= eva <= 120 and step_raw >= 0:
        return 0, "B"
    if -dead // 2 <= err <= dead // 2:
        return 0, "dead"
    if step_raw > limit:
        return limit, "C(限幅+)"
    if step_raw < -limit:
        return -limit, "C(限幅-)"
    return step_raw, "C"


def main() -> int:
    import app as m
    import pt_tables as pt
    from pyocd.core.helpers import ConnectHelper

    do_list = "--list" in sys.argv
    do_restore = "--restore" in sys.argv
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = set(sys.argv[i + 1].split(",")) if i + 1 < len(sys.argv) else None

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    def rd(addr, n=1):
        for _ in range(4):
            try:
                return client.read_holding_registers(SLAVE, addr, n)
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        return [-1] * n

    def s16(v):
        v &= 0xFFFF
        return v - 0x10000 if v & 0x8000 else v

    def wr(addr, val) -> tuple[bool, float]:
        """网关写。⚠ 判据只看镜像回读==目标值（状态位会读到上一轮遗留，§21.8）。"""
        t0 = time.time()
        try:
            client.write_single_register(SLAVE, addr, val & 0xFFFF)
        except Exception as exc:  # noqa: BLE001
            say(f"      !! 写 [{addr}]={val} 抛异常: {exc}")
            return False, time.time() - t0
        while time.time() - t0 < 45:
            time.sleep(0.5)
            if s16(rd(addr)[0]) == val:
                return True, time.time() - t0
        return False, time.time() - t0

    # ---------------- ST-Link ----------------
    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"})
    if session is None:
        say("!! 没找到 ST-Link"); write_out(); return 1
    session.open()
    tgt = session.target
    if tgt.get_state() == tgt.State.HALTED:
        say("!! 进入时 HALTED —— 已 resume"); tgt.resume()

    def r16(a):
        b = tgt.read_memory_block8(a, 2)
        return b[0] | (b[1] << 8)

    def ps(i):
        v = r16(PARAM_BASE + i * 2)
        return v - 0x10000 if v & 0x8000 else v

    def ai(i):
        v = r16(A_AI + i * 2)
        return v - 0x10000 if v & 0x8000 else v

    def r32s(a):
        b = tgt.read_memory_block8(a, 4)
        v = b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
        return v - 0x100000000 if v & 0x80000000 else v

    def r64s(a):
        """⚠ 必须做符号扩展。缺了它负的 EEVSpecResidualMilli 会变成 ~2^64，
        汇总里就会出现「原值18446744073709548」这种鬼数字。"""
        v = ((r32s(a + 4) & 0xFFFFFFFF) << 32) | (r32s(a) & 0xFFFFFFFF)
        return v - (1 << 64) if v & (1 << 63) else v

    # ================= 0. 自检 =================
    say("=" * 78)
    say("316 外机电子膨胀阀 §3.9 一致性 —— 真机测试")
    say("=" * 78)
    say()
    fp = [ps(1000 + i) for i in range(6)]
    say(f"  版本指纹 [1000..1005] = {fp}")
    if fp[0] != 316 or fp[1] != 12:
        say("  [NG] 不像 316 V12.x —— 基址不对或挂错板。退出，不写任何东西。")
        write_out(); return 1
    say(f"  工作模式 [1] = {ps(P_WMODE)} ({WM.get(ps(P_WMODE), '?')})"
        f"   PID使能 [200] = {ps(P_PIDEN)}")

    params = dict(Y=ps(P_Y), YD=ps(P_YD), KP=ps(P_KP), TP=ps(P_TP), TI=ps(P_TI),
                  TD=ps(P_TD), START=ps(P_START), LIMIT=ps(P_LIMIT),
                  MAXOPEN=ps(P_MAXOPEN))
    say()
    say("  参数       实值    规格值   判定")
    say("  ----------|-------|--------|-----")
    allok = True
    for k in ("Y", "YD", "KP", "TP", "TI", "TD", "START", "LIMIT", "MAXOPEN"):
        ok = params[k] == SPEC[k]
        allok &= ok
        unit = "C(x0.1)" if k in ("Y", "YD") else ""
        say(f"  {k:<10}| {params[k]:>5} | {SPEC[k]:>6} | {'[OK]' if ok else '[NG]'} {unit}")
    say()
    if not allok:
        say("  [+] 参数与规格书默认值不同 —— 下面按**实测参数**判定，不按规格值。")
    say(f"  化霜开度 [21] = {ps(P_DEFOPEN)} (规格 350)   制冷剂 [39] = {ps(P_REFRIG)}")

    blk = []
    if ps(P_WMODE) != 1:
        blk.append("工作模式不是制热（规格书：热泵制热时室外 EEV 才按吸气过热度控制）")
    if ps(P_PIDEN) != 1:
        blk.append("PID 使能 [200] != 1（走的是老 6 级阶梯，不是规格书 PID）")
    comp = list(tgt.read_memory_block8(A_COMP, 2))
    if not any(comp):
        blk.append(f"压机没在转 Comp={comp}（EEVSpecAutoAction 门禁要求 running）")
    say(f"  压机 Comp = {comp}")
    if blk:
        say()
        say("  [NG] 前提不满足，拒绝跑：")
        for b in blk:
            say(f"     - {b}")
        if tgt.get_state() == tgt.State.HALTED:
            tgt.resume()
        session.close(); client.close(); write_out(); return 2

    say(f"  注入地址：NTC[5] 偏移 = 330[{NTC5_OFF}]   ch2 AiCfgOffset = 330[{EVA_OFF}]")
    say(f"  基准读数：吸气 {ai(11)/10.0:.1f}C  蒸发 {ps(P_EVA1)/10.0:.1f}C  "
        f"过热度 {ps(P_OVER1)/10.0:.1f}C")

    if do_list:
        say()
        say("  测点清单（--list）：")
        for g, eva, sh, want, why in POINTS:
            say(f"    [{g}] 蒸发{eva/10:5.1f}C 过热度{sh/10:5.1f}C -> 期望 {want:<8} {why}")
        if tgt.get_state() == tgt.State.HALTED:
            tgt.resume()
        session.close(); client.close(); write_out(); return 0

    # ================= 还原模式 =================
    eva_off0 = s16(rd(EVA_OFF)[0])
    ntc_off0 = s16(rd(NTC5_OFF)[0])
    if do_restore:
        say()
        say(f"  --restore：NTC[5] 偏移 -> {ntc_off0}，ch2 AiCfgOffset -> {eva_off0}")
        say("  (这两个值就是脚本读到的当前值；若要强制归零请用 rw330.py 直接写)")
        if tgt.get_state() == tgt.State.HALTED:
            tgt.resume()
        session.close(); client.close(); write_out(); return 0

    # ================= 1. 标定 ch2 偏移 -> 低压 kPa =================
    # 蒸发温度走的是「偏移 -> AI[2] -> Filter_A[0](kPa) -> 饱和温度表」这条链。
    # 后一段是非线性的（查表），所以不能对温度做线性外推。
    # 正确做法：直接读 Filter_A[0]（就是 kPa），标定「偏移 -> kPa」这一段
    # （这一段是线性的，AI 换算），再用 PT 表反查目标温度对应的 kPa。
    refrig = {0: pt.R22, 1: pt.R134A, 2: pt.R407C, 3: pt.R410A}.get(ps(P_REFRIG), pt.R410A)
    refrig_name = {0: "R22", 1: "R134A", 2: "R407C", 3: "R410A"}.get(ps(P_REFRIG), "?")

    def kpa_at_temp(target_01: int) -> int:
        """反查：要得到目标饱和温度(0.1C)需要多少 kPa。表是单调的，线性扫即可。"""
        best, bd = 0, 1 << 30
        for kpa in range(-100, pt.pressure_max_kpa(refrig) + 1, 1):
            d = abs(pt.pt_temp_x10(refrig, kpa) - target_01)
            if d < bd:
                bd, best = d, kpa
            elif d > bd:
                break
        return best

    say()
    say("=" * 78)
    say(f"1. 标定：ch2 AiCfgOffset -> 低压 kPa（制冷剂 {refrig_name}）")
    say("=" * 78)
    off0 = eva_off0
    kpa0 = r16(A_FILTERA)                       # Filter_A[0]，单位 kPa
    say(f"  基线：偏移 {off0}  ->  低压 Filter_A[0] = {kpa0} kPa  "
        f"(饱和温度 {pt.pt_temp(refrig, kpa0):.1f}C)")
    CAL = 200
    say(f"  写 [{EVA_OFF}] = {off0 + CAL}  (Δ=+{CAL}) ...")
    ok, el = wr(EVA_OFF, off0 + CAL)
    say(f"    {'OK' if ok else '[NG] 超时'}  {el:.1f}s")
    time.sleep(9)                               # Filter_A 是 8 拍平均
    kpa1 = r16(A_FILTERA)
    slope_kpa = (kpa1 - kpa0) / CAL             # kPa 每 偏移单位
    say(f"  低压 {kpa0} -> {kpa1} kPa   (Δ={kpa1-kpa0:+d} 每 +{CAL} 偏移)")
    say(f"  >>> 斜率 = {slope_kpa:.4f} kPa/单位")
    say(f"  写回原值 {off0} 还原 ...")
    ok, el = wr(EVA_OFF, off0)
    say(f"    {'OK' if ok else '[NG] 超时'}  {el:.1f}s")
    time.sleep(9)
    if abs(slope_kpa) < 1e-6:
        say("  [NG] 斜率为 0 —— 注入通道没起作用，退出（不改任何东西）")
        if tgt.get_state() == tgt.State.HALTED:
            tgt.resume()
        session.close(); client.close(); write_out(); return 2

    def off_for_eva(target_01: int) -> int:
        """反算：要得到目标蒸发温度(0.1C)该写多少偏移。"""
        kpa_t = kpa_at_temp(target_01)
        return int(round(off0 + (kpa_t - kpa0) / slope_kpa))

    # ================= 2. 逐点造工况 =================
    say()
    say("=" * 78)
    say("2. 逐点造工况 + 对拍")
    say("=" * 78)
    say()
    say("   测点 | 目标蒸发 实得 | 过热度 | E0   E1   E2 | 规格书 固件步 | 判定")
    say("  ------|---------------|--------|---------------|--------------|-----")

    result = []
    for grp, eva_t, sh_t, want, why in POINTS:
        if only and grp not in only:
            continue
        # --- 先设蒸发温度 ---
        ok1, _ = wr(EVA_OFF, off_for_eva(eva_t))
        time.sleep(9)                               # Filter_A 8 拍平均
        eva_act = ps(P_EVA1)
        # --- 再把吸气温度设到 蒸发 + 目标过热度（这条 1:1 线性，一次到位）---
        ntc_new = s16(rd(NTC5_OFF)[0]) + ((eva_act + sh_t) - ai(11))
        ok2, _ = wr(NTC5_OFF, ntc_new)
        time.sleep(7)                               # 等一个 PID 周期（TP=5s）+ 余量

        # --- 读固件内部状态 ---
        e0 = r32s(A_ERRHIST + 0)
        e1 = r32s(A_ERRHIST + 4)
        e2 = r32s(A_ERRHIST + 8)
        resid = r64s(A_RESID + 0)
        eva_f, sh_f = ps(P_EVA1), ps(P_OVER1)
        err = sh_f - ps(P_Y)
        fw_step = ps(P_E1STEP)                      # ★ 固件自己算出的步数
        fw_err = ps(P_E1ERR)                        # ★ 固件自己算出的 E(K)

        # --- PC 侧按规格书重算（用固件自己的 E 序列）---
        scaled = spec_scaled(e0, e1, e2, ps(P_KP), ps(P_TP), ps(P_TI), ps(P_TD))
        raw = tdiv(scaled, 1000)                    # 未含余量累加的 PID 原值
        exp, branch = judge(raw, eva_f, err, ps(P_LIMIT), ps(P_YD))

        # 工况容差：边界测点（12.0/12.1、10.0/9.9、死区边）必须咬得很紧，
        # 否则「没造准工况」会冒充「固件不符」。目标值带 .0/.1 的用 ±0.2C，
        # 其余 ±0.5C。
        tol = 2 if (eva_t % 10) in (0, 1) else 5
        cond_ok = abs(eva_act - eva_t) <= tol
        # 步数判据：余量绝对值恒 <1000，所以固件步数 ∈ {raw, raw±1}
        step_ok = abs(fw_step - exp) <= 1
        # E(K)：固件诊断是**上一次 PID 拍**算的，最多差一个 TP(5s)，
        # 期间过热度会漂，所以只做粗校验（±3 = 0.3C）
        err_ok = abs(fw_err - err) <= 3
        ok = step_ok and err_ok and cond_ok
        mark = "[OK]" if ok else "[NG]"

        say(f"   {grp:<4} | {eva_t/10:5.1f} ->{eva_f/10:5.1f} | {sh_f/10:5.1f} |"
            f" {e0:4d} {e1:4d} {e2:4d} | {exp:5d} {fw_step:6d} | {mark} {branch} vs {want}")
        if not step_ok:
            say(f"        [NG] 步数对不上：规格书算 {exp}，固件给 {fw_step}")
        if not err_ok:
            say(f"        [NG] E(K) 对不上：过热度-Y = {err}，固件诊断 = {fw_err}")
        if not cond_ok:
            say(f"        [+] 工况没造准（目标 {eva_t/10:.1f}C，实得 {eva_f/10:.1f}C，"
                f"差 {(eva_f-eva_t)/10:+.1f}C）—— 分支结论仍按实得值判")
        if ok and branch != want:
            say(f"        [+] 分支是 {branch} 不是预期的 {want} —— 因为工况偏了，逻辑本身没错")
        if not (ok1 and ok2):
            say(f"        [+] 本次写有超时 (eva={ok1} ntc={ok2})")
        result.append((grp, want, branch, ok, eva_f, sh_f, raw, exp, fw_step, why))

    # ================= 3. 还原 =================
    say()
    say("=" * 78)
    say("3. 还原")
    say("=" * 78)
    ok, el = wr(EVA_OFF, eva_off0)
    say(f"  ch2 AiCfgOffset -> {eva_off0}  {'OK' if ok else '[NG] 超时'}  {el:.1f}s")
    ok, el = wr(NTC5_OFF, ntc_off0)
    say(f"  NTC[5] 偏移    -> {ntc_off0}  {'OK' if ok else '[NG] 超时'}  {el:.1f}s")
    time.sleep(9)
    say(f"  还原后：吸气 {ai(11)/10.0:.1f}C  蒸发 {ps(P_EVA1)/10.0:.1f}C  "
        f"过热度 {ps(P_OVER1)/10.0:.1f}C")

    # ================= 4. 汇总 =================
    say()
    say("=" * 78)
    say("4. 汇总")
    say("=" * 78)
    bad = [r for r in result if not r[3]]
    say(f"  测点 {len(result)} 个，通过 {len(result)-len(bad)}，不符 {len(bad)}")
    if bad:
        say()
        say("  不符项：")
        for grp, w, g, _, eva, sh, raw, exp, new, why in bad:
            say(f"    [{grp}] 蒸发{eva/10:.1f}C 过热度{sh/10:.1f}C："
                f"期望 {w}，实得 {g}  (原值{raw} 期望步数{exp} 固件目标{new})")
    else:
        say("  [OK] 全部与规格书 §3.9 一致")

    if tgt.get_state() == tgt.State.HALTED:
        say("!! 结束 HALTED —— resume"); tgt.resume()
    say(f"\n结束 state={tgt.get_state().name}")
    session.close(); client.close(); write_out()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
