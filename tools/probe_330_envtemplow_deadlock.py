# -*- coding: utf-8 -*-
"""330 送风低温保护（[621]）死锁的实机判别 —— 旧固件 vs V10.14。

## 判据（这是本探针唯一要回答的问题）

    [621] 置位后，切到非制冷工况，释放条件满足时它能不能自己清 0？

- **V10.13 及以前**：释放行在 `if(UserWorkModeSet==0)` 里 ⇒ 切到制热/通风后不可达
  ⇒ `[621]` 永远是 1 ⇒ `SysErrStatus=1` ⇒ `SysStep` 卡 4 ⇒ **机组开不了机**
- **V10.14**：释放已移到 `if/else` 之后 ⇒ 任何模式都能清

## ⚠ 测试设计的关键点（第一版设计错了）

释放条件是 `SysOutTempAI10Disp >= [201]+[205]`（默认 3.0+3.0 = **6.0 °C**）。
所以**光切模式不够** —— 如果注入还在（送风被压到 2.5 °C），新旧固件都不会清，
**测不出任何区别**。必须在切模式之后**同时撤掉注入**，让送风回到 6.0 °C 以上：

    1) 制冷 + 注入 [494]  ⇒ 送风 ≤ 3.0 °C 连续 2s ⇒ [621]=1、SysStep=4
    2) 切 [236]=1（制热）
    3) 撤注入 [494] 归零    ⇒ 送风回到 ~27 °C，释放条件满足
    4) 看 [621]：旧=1（锁死）  新=0（解开）

## 注入链

`[494] UserA6ValueSet` 是 NTC1 **送风** 的校准偏移（0.1 °C，叠加不是替换），
`[510]` 显示值 = 真值 + 偏移。所以按实时 `[510]` 反推偏移，避免温度漂移：

    新偏移 = 旧偏移 + (目标显示值 - 当前显示值)     目标 = 2.5 °C = 25

写入限幅 `NTC_CALIBRATION_LIMIT_TENTHS_C = 500`（`[484..495]`，见 modbus.c:278）。

## 跑法

    python.exe tools/probe_330_envtemplow_deadlock.py --phase=A     # 旧固件（复现 BUG）
    # 烧录 V10.14
    python.exe tools/probe_330_envtemplow_deadlock.py --phase=B     # 新固件（验证修复）

A 相结束时机组处于 `SysStep=4` 锁死态 —— **这是预期的**，烧录会复位它。
任何异常路径都会在 finally 里把 `[236]/[493]/[494]/[495]` 还原。
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1
OUT = pathlib.Path(__file__).resolve().with_suffix(".txt")

# ---- 寄存器 ----
R_MODE, R_SYSSTEP, R_ONOFF = 236, 709, 398
R_ERRSTATUS, R_LOWERR, R_FINGERPRINT = 710, 621, 885
R_SUPPLY = 510                      # 显示 送风温度 NTC1（0.1C）
R_LOWSET, R_GAP, R_DEBOUNCE = 201, 205, 25
R_RESET = 524
R_VER_BASE = 2622                   # PSC330_VERSION_HMI_BASE：6 字，model/major/minor/y/m/d
R_OFF = {493: "新风 NTC2", 494: "送风 NTC1", 495: "房间 NTC0"}

TARGET_DISP = 25                    # 2.5 °C，比阈值 3.0 °C 低 0.5 °C
MODE_COOL, MODE_HEAT = 0, 1
MODE_NAME = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排毒", 5: "自动消排毒"}

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode("gbk", "replace").decode("gbk", "replace"), flush=True)
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def main() -> int:
    import app as m

    phase = "A"
    for a in sys.argv[1:]:
        if a.startswith("--phase="):
            phase = a.split("=", 1)[1].upper()

    import serial.tools.list_ports as lp
    have = [p.device for p in lp.comports()]
    if PORT not in have:
        say("✗ %s 不在（现有 %s），退出" % (PORT, have))
        return 1

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    def rd(a):
        for _ in range(3):
            try:
                return s16(client.read_holding_registers(SLAVE, a, 1)[0])
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        return None

    def wr(a, v):
        """底层写，绕过 app.py 的模式校验链。**值相同则不写** ——
        无谓地重写 [236] 会重置启动时序（SysStep 退回 1 重跑开阀延时）。"""
        if rd(a) == s16(v):
            return True
        for _ in range(3):
            try:
                client.write_single_register(SLAVE, a, v & 0xFFFF)
                time.sleep(0.4)
                return rd(a) == s16(v)
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        return False

    snap = {a: rd(a) for a in (R_MODE, R_ONOFF, 493, 494, 495)}
    ver = [rd(R_VER_BASE + i) for i in range(6)]
    fw = "V%s.%s %s-%s-%s" % (ver[1], ver[2], ver[3], ver[4], ver[5])
    say("=== 330 送风低温保护死锁判别 —— 相 %s ===" % phase)
    say("板上固件：**%s**（model %s，[2622..2627]）" % (fw, ver[0]))
    # 探针第一版没核版本就下结论，在"以为测旧固件、实际板上是新固件"时给出假阳性。
    if phase == "A" and (ver[1], ver[2]) >= (10, 14):
        say("⚠ 相 A 本意是**复现旧固件的死锁**，但板上已是 V10.14 —— 这轮测的是修复后的行为。")
        say("  要拿对照组必须先把 V10.13 烧回去。")
    if phase == "B" and (ver[1], ver[2]) < (10, 14):
        say("⚠ 相 B 本意是验证修复，但板上还是 V10.13 —— 结论会反向。")
    say("")
    say("快照：模式=%s(%s) 启停=%s  [493]=%s [494]=%s [495]=%s"
        % (snap[R_MODE], MODE_NAME.get(snap[R_MODE]), snap[R_ONOFF],
           snap[493], snap[494], snap[495]))
    say("")

    try:
        # ---------- 前置：制冷 + 运行中 ----------
        say("-- 前置条件 --")
        if snap[R_MODE] != MODE_COOL:
            say("  模式不是制冷，切到制冷")
            wr(R_MODE, MODE_COOL)
            time.sleep(3)
        if snap[R_ONOFF] != 1:
            say("  置启停=1")
            wr(R_ONOFF, 1)
        step = rd(R_SYSSTEP)
        if step != 2:
            say("  等 SysStep 到 2（最多 90 秒，当前 %s）..." % step)
            t0 = time.time()
            while time.time() - t0 < 90:
                step = rd(R_SYSSTEP)
                if step == 2:
                    break
                time.sleep(1.0)
            say("  等待 %.0fs 后 [709] SysStep = %s" % (time.time() - t0, step))
        say("  [709] SysStep = %s（需 == 2 运行中）" % step)
        if step != 2:
            say("  ✗ 未运行，退出（请先让机组进入制冷运行）")
            return 2

        # ---------- 1) 注入，把送风压到 2.5 °C ----------
        say("")
        say("-- 1) 注入 [494]，把送风压到 %.1f °C --" % (TARGET_DISP / 10.0))
        disp = rd(R_SUPPLY)
        off = rd(494)
        say("  注入前：[510] 送风显示 = %.1f °C，[494] = %s" % (disp / 10.0, off))
        new_off = off + (TARGET_DISP - disp)
        new_off = max(-500, min(500, new_off))
        say("  → [494] = %d（目标显示 %.1f °C）" % (new_off, TARGET_DISP / 10.0))
        if not wr(494, new_off):
            say("  ✗ [494] 写入失败（限幅 ±500？），退出")
            return 2
        time.sleep(1)
        say("  注入后：[510] = %.1f °C" % (rd(R_SUPPLY) / 10.0))

        # ---------- 2) 等置位 ----------
        say("")
        say("-- 2) 等 [621] 置位（阈值 [201]=%s，去抖 [25]=%s 秒）--"
            % (rd(R_LOWSET), rd(R_DEBOUNCE)))
        trip_t = None
        t0 = time.time()
        while time.time() - t0 < 30:
            if rd(R_LOWERR) == 1:
                trip_t = time.time() - t0
                break
            time.sleep(0.3)
        if trip_t is None:
            say("  ✗ 30 秒内 [621] 未置位 —— 送风没压到阈值以下？退出")
            return 2
        say("  ✓ [621] = 1（用时 %.1fs）" % trip_t)
        time.sleep(1.5)
        step_after = rd(R_SYSSTEP)
        say("  [709] SysStep = %s   [710] SysErrStatus = %s   [885] 指纹 = %s"
            % (step_after, rd(R_ERRSTATUS), rd(R_FINGERPRINT)))
        if step_after != 4:
            say("  ⚠ SysStep 不是 4，现象链与预期不同，继续观察")

        # ---------- 3) 切到制热 ----------
        say("")
        say("-- 3) 切到制热（[236]=1）--")
        if not wr(R_MODE, MODE_HEAT):
            say("  ✗ 模式写入失败，退出")
            return 2
        time.sleep(2)
        say("  [236] = %s（%s）" % (rd(R_MODE), MODE_NAME.get(rd(R_MODE))))

        # ---------- 4) 撤注入：让送风回到阈值以上 ----------
        say("")
        say("-- 4) 撤注入 [494] → %s，让送风回阈值以上 --" % snap[494])
        if not wr(494, 0):
            say("  ⚠ [494] 归零失败，退回原值")
            wr(494, snap[494])
        time.sleep(2)
        disp2 = rd(R_SUPPLY)
        need = rd(R_LOWSET) + rd(R_GAP)
        say("  [510] 送风 = %.1f °C，释放门槛 = %s + %s = %.1f °C  ⇒ 条件%s"
            % (disp2 / 10.0, rd(R_LOWSET), rd(R_GAP), need / 10.0,
               "满足" if disp2 >= need else "**不满足**（这样测不出差别）"))

        # ---------- 5) 观察 ----------
        say("")
        say("-- 5) 观察 15 秒：切到制热且释放条件满足后，[621] 会不会自己清 --")
        cleared_t = None
        t0 = time.time()
        while time.time() - t0 < 15:
            if rd(R_LOWERR) == 0:
                cleared_t = time.time() - t0
                break
            time.sleep(0.3)
        final_step = rd(R_SYSSTEP)
        if cleared_t is not None:
            say("  ✓ [621] 在 %.1fs 后自行清 0" % cleared_t)
            say("  [709] SysStep = %s   [710] SysErrStatus = %s" % (final_step, rd(R_ERRSTATUS)))
            say("")
            say("  ⇒ 固件 %s：**释放可达**。" % fw)
            say("     对照判据：V10.13 里该变量全仓只有两个写点（置位与释放），")
            say("     都在 `if(UserWorkModeSet==0)` 内 ⇒ 切模式后无任何代码能写它，")
            say("     旧固件在本序列下必然是 1。本轮未烧回 V10.13 做硬件对照。")
        else:
            say("  ✗ 15 秒内 [621] 始终为 1")
            say("  [709] SysStep = %s   [710] SysErrStatus = %s" % (final_step, rd(R_ERRSTATUS)))
            say("")
            say("  ⇒ 固件 %s：**释放不可达 / 未生效**。" % fw)
        return 0

    finally:
        say("")
        say("-- 还原 --")
        for a in (493, 494, 495):
            if snap[a] is not None:
                ok = wr(a, snap[a])
                say("  [%d] <- %s  %s" % (a, snap[a], "ok" if ok else "**失败**"))
        if snap[R_MODE] is not None:
            ok = wr(R_MODE, snap[R_MODE])
            say("  [236] <- %s (%s)  %s"
                % (snap[R_MODE], MODE_NAME.get(snap[R_MODE]), "ok" if ok else "**失败**"))
        if snap[R_ONOFF] is not None:
            ok = wr(R_ONOFF, snap[R_ONOFF])
            say("  [398] 启停 <- %s  %s" % (snap[R_ONOFF], "ok" if ok else "**失败**"))
        say("  提示：若本相在切模式后终止，机组可能停在 SysStep=4；")
        say("        脉冲 [524]（先写 1 再写 0）即可解除。")
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
