# -*- coding: utf-8 -*-
"""PSC330 内机 §3.4 定频压缩机加减载 —— **真机测试**（一次性排查用）。

配套 sim_330_comp_stage.py（离线仿真）。本脚本在板上真跑的固件上验。

## 当前测的是 §3.4.1 环境温度控制

控制依据 `[315] CompControlModeSet`：
    0 = 室内温湿度 PID      1 = 环境温度控制

环境控制用**新风温度** `[512] FreshAirTempDisp` 决策。它可注入：
    [512] = NTC2 显示值 = 真实值 + 校准偏移 [493]
    ⇒ 要设成目标 X：写 [493] += (X - 当前[512])

## 判据（规格书 §3.4.1，用户 2026-10-14 更正版）

    制热：新风 <= HRM[318] → 满载 CN；>= HRC[319] → 空载 0；
          中间 → MIN(CN, ROUNDUP(CN*(HRC-T)/(HRC-HRM)))
    制冷：新风 >= HLM[316] → 满载 CN；<= HLC[317] → 空载 0；
          中间 → MIN(CN, ROUNDUP(CN*(T-HLC)/(HLM-HLC)))

观测寄存器：
    [880] IndoorPidNDisp       PID 能力需求 N（千分制）—— 环境控制下不更新
    [881] IndoorTargetCompDisp **目标台数** ← 判据看这个
    [119] CompNumCur           330 认为在跑的台数
    [707] SystemNengry         加/减载命令
    [872] IndoorCtrlModeDisp   0=室内PID 1=环境控制

⚠ 只测**决策层**（[881] 目标台数）。真正加减一台受最小停机 180s / 最小开机 180s /
  开关间隔 30s 约束，要看 [119] 追上去得等好几分钟 —— 那是另一回事（§55.1 的 C1~C7）。

跑法：
    python.exe tools/test_330_comp_stage.py             # 扫当前模式
    python.exe tools/test_330_comp_stage.py --dry       # 只看现状，不写注入
    python.exe tools/test_330_comp_stage.py --restore   # 只还原注入
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1

# ---- 330 Parameter 下标 ----
P_MODE = 1                  # UserWorkModeSet（0=制冷 1=制热）
P_CN_MODE = 315             # CompControlModeSet
P_HLM, P_HLC, P_HRM, P_HRC = 316, 317, 318, 319
P_WD_C, P_WD_H = 160, 161
P_TARGET = 881              # IndoorTargetCompDisp
P_N = 880                   # IndoorPidNDisp
P_CUR = 119                 # CompNumCur
P_CMD = 707                 # SystemNengry
P_CTRLMODE = 872            # IndoorCtrlModeDisp
P_FRESH = 512               # FreshAirTempDisp 新风温度（0.1C）
P_FRESH_OFF = 493           # 它的校准偏移

MODE_NAME = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排风", 5: "自动"}

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "gbk"
        print(s.encode(enc, "replace").decode(enc, "replace"), flush=True)


def write_out() -> None:
    p = pathlib.Path(os.environ.get("TEMP", ".")) / "test_330_comp_stage.txt"
    p.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"\n[报告] {p}", flush=True)


def spec_target(mode: int, t: int, cn: int, hlm: int, hlc: int,
                hrm: int, hrc: int) -> tuple[int, str]:
    """规格书 §3.4.1 的期望目标台数。t = 新风温度(0.1C)。"""
    if mode == 0:                                   # 制冷
        if t >= hlm:
            return cn, "满载(>=HLM)"
        if t <= hlc:
            return 0, "空载(<=HLC)"
        return min(cn, -(-cn * (t - hlc) // (hlm - hlc))), "线性"
    if mode == 1:                                   # 制热
        if t <= hrm:
            return cn, "满载(<=HRM)"
        if t >= hrc:
            return 0, "空载(>=HRC)"
        return min(cn, -(-cn * (hrc - t) // (hrc - hrm))), "线性"
    return 0, "非冷非热"


def main() -> int:
    import app as m

    dry = "--dry" in sys.argv
    only_restore = "--restore" in sys.argv

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

    def r16(a):
        return s16(rd(a)[0])

    def wr(a, v):
        client.write_single_register(SLAVE, a, v & 0xFFFF)
        time.sleep(0.15)
        return r16(a)

    say("=" * 78)
    say("PSC330 §3.4.1 环境温度控制 —— 真机测试")
    say("=" * 78)
    say()

    # ---------------- 0. 自检 ----------------
    mode = r16(P_MODE)
    cnmode = r16(P_CN_MODE)
    hlm, hlc, hrm, hrc = (r16(P_HLM), r16(P_HLC), r16(P_HRM), r16(P_HRC))
    ctrl = r16(P_CTRLMODE)
    fresh0 = r16(P_FRESH)
    off0 = r16(P_FRESH_OFF)

    say(f"  工作模式 [1]        = {mode} ({MODE_NAME.get(mode, '?')})")
    say(f"  控制依据 [315]      = {cnmode}  ({'环境温度控制' if cnmode == 1 else '室内温湿度PID'})")
    say(f"  控制模式显示 [872]  = {ctrl}  (0=室内PID 1=环境控制)")
    say(f"  HLM[{P_HLM}]={hlm/10:.1f}C  HLC[{P_HLC}]={hlc/10:.1f}C  "
        f"HRM[{P_HRM}]={hrm/10:.1f}C  HRC[{P_HRC}]={hrc/10:.1f}C")
    say(f"  新风温度 [512]      = {fresh0/10:.1f}C   校准偏移 [{P_FRESH_OFF}] = {off0}")
    say(f"  目标台数 [881]      = {r16(P_TARGET)}   "
        f"当前台数 [119] = {r16(P_CUR)}   命令 [707] = {r16(P_CMD)}")
    say()

    blk = []
    if cnmode != 1:
        blk.append(f"[315]={cnmode} —— 不是环境温度控制（要 1），本脚本测的是 §3.4.1")
    if ctrl != 1:
        blk.append(f"[872]={ctrl} —— 固件实际没走环境控制分支")
    if mode not in (0, 1):
        blk.append(f"[1]={mode} —— 不是制冷/制热")
    if blk:
        say("  [NG] 前提不满足：")
        for b in blk:
            say(f"     - {b}")
        if dry or only_restore:
            pass
        else:
            say("     ⇒ 只做只读汇报，不写任何注入。")
        client.close()
        write_out()
        return 2

    if only_restore:
        say("  --restore：本次没有残留注入需要还原（见下方还原段）")
        say(f"     [493] 当前 = {r16(P_FRESH_OFF)}（原值 {off0}）")

    if dry:
        say("  --dry：只看现状，不扫。")
        client.close()
        write_out()
        return 0

    # ---------------- 1. 标定 [493] -> [512] ----------------
    say("=" * 78)
    say("1. 标定：[493] 校准偏移 -> [512] 新风温度")
    say("=" * 78)
    CAL = 100
    wr(P_FRESH_OFF, off0 + CAL)
    time.sleep(2.0)
    fresh1 = r16(P_FRESH)
    slope = (fresh1 - fresh0) / CAL
    say(f"  写 [{P_FRESH_OFF}] = {off0 + CAL}  ⇒  [512] {fresh0/10:.1f}C -> {fresh1/10:.1f}C")
    say(f"  >>> 斜率 = {slope:.3f} (0.1C 每 偏移单位)")
    wr(P_FRESH_OFF, off0)
    time.sleep(2.0)
    if abs(slope - 1.0) > 0.05:
        say(f"  [NG] 斜率不是 1.0 —— 注入链路可能不对，退出（已还原）")
        client.close()
        write_out()
        return 2
    say("  [OK] 1:1 线性，链路可用")
    say()

    # ---------------- 2. 判 CN ----------------
    # 把新风推到**满载区**，读 [881] 即 CN。
    # ⚠ 方向别搞反：制热满载在**低温**侧（<=HRM），制冷满载在**高温**侧（>=HLM）。
    full_t = (hrm - 50) if mode == 1 else (hlm + 50)
    wr(P_FRESH_OFF, off0 + (full_t - fresh0))
    time.sleep(2.5)
    cn = r16(P_TARGET)
    say(f"  推到满载区（新风 {r16(P_FRESH)/10:.1f}C）⇒ [881] = {cn}  ⇒ **CN = {cn}**")
    wr(P_FRESH_OFF, off0)
    time.sleep(2.0)
    say()

    # ---------------- 3. 扫新风温度 ----------------
    say("=" * 78)
    say(f"2. 扫新风温度（模式={MODE_NAME[mode]}，CN={cn}）")
    say("=" * 78)
    say()
    say("   新风温度 | [881]实得 | 规格书期望 | 分支 | 判定 | [119] [707]")
    say("  ----------|-----------|------------|------|------|------------")

    if mode == 1:
        pts = sorted({hrm - 60, hrm - 10, hrm - 1, hrm, hrm + 1,
                      hrm + (hrc - hrm) // 4, (hrm + hrc) // 2,
                      hrm + (hrc - hrm) * 3 // 4, hrc - 1, hrc, hrc + 1, hrc + 50})
    else:
        pts = sorted({hlc - 60, hlc - 10, hlc - 1, hlc, hlc + 1,
                      hlc + (hlm - hlc) // 4, (hlc + hlm) // 2,
                      hlc + (hlm - hlc) * 3 // 4, hlm - 1, hlm, hlm + 1, hlm + 50})

    bad = []
    for t in pts:
        wr(P_FRESH_OFF, off0 + (t - fresh0))
        time.sleep(1.8)
        got_t = r16(P_FRESH)
        got = r16(P_TARGET)
        cur, cmd = r16(P_CUR), r16(P_CMD)
        exp, branch = spec_target(mode, got_t, cn, hlm, hlc, hrm, hrc)
        ok = got == exp
        if not ok:
            bad.append(f"新风{got_t/10:.1f}C 实得{got} 期望{exp}({branch})")
        say(f"   {got_t/10:8.1f} | {got:9d} | {exp:10d} | {branch:<10} | "
            f"{'[OK]' if ok else '[NG]'} | {cur:4d} {cmd:4d}")

    # ---------------- 4. 还原 ----------------
    say()
    say("=" * 78)
    say("3. 还原")
    say("=" * 78)
    back = wr(P_FRESH_OFF, off0)
    time.sleep(2.0)
    say(f"  [{P_FRESH_OFF}] -> {back}   [512] = {r16(P_FRESH)/10:.1f}C   "
        f"[881] = {r16(P_TARGET)}   [119] = {r16(P_CUR)}")

    # ---------------- 5. 汇总 ----------------
    say()
    say("=" * 78)
    say("4. 汇总")
    say("=" * 78)
    n = len(pts)
    say(f"  测点 {n} 个，通过 {n - len(bad)}，不符 {len(bad)}")
    if bad:
        say()
        say("  不符项：")
        for b in bad:
            say(f"     {b}")
    else:
        say("  [OK] 全部与规格书 §3.4.1 一致")
    say()
    say("  [!] 本脚本只验**决策层**（[881] 目标台数）。")
    say("     真正加减一台受最小停机 180s / 最小开机 180s / 间隔 30s 约束，")
    say("     看 [119] 追上去要等好几分钟 —— 那属于 §55.1 的 C1~C7。")
    say()
    client.close()
    write_out()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
