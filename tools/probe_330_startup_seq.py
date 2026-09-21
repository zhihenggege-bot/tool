# -*- coding: utf-8 -*-
"""330 §3.3 机组开关机逻辑 —— 序列时序探针（逐段计时 + 风阀/风机实际动作）。

规格书 §3.3.1/3.3.2/3.3.3 把开机/关机写成一串带延时的步骤。
固件把"当前走到哪一步"暴露在 `DisinfectStepDisp = Parameter[885]` 上，正好可以逐段计时：

    开机（IndoorNormalStartSequence, UserAction.c:1352-1403）
        stepBase + 1 = 阶段1  风阀全开，等 valveDelay（有风阀 150s / 无风阀 10s）
        stepBase + 5 = 阶段5  风机全开，等压差开关**持续闭合 10s**
        stepBase = 110 制冷 / 120 制热 / 130 通风 / 100 其他

    关机（SysBoardAction case 3/4/5, UserAction.c:2326-2409）
        201 = 加湿器关闭后等 30s（恒温恒湿时）
        202 = 再热/预热关闭 + 等外机停稳
        203 = 逆序停风机（送→30s→回→30s→排）
        205 = 风机停完后再等 30s
        206 = 风阀关闭完成

    掉线/故障快速关机路径（IndoorDisinfectExhaustAction step 10~14）
        210 / 211 / 212 / 214 与上面 201/202/203/205 一一对应

开/关机命令寄存器是 **`[398] HMIOnOffCommandSet`（0=停 / 1=开）**，由 `--cycle` 自己写；
不加 `--cycle` 时你也可以另开命令行触发：
    python.exe tools/rw330.py 398=1      # 开机
    python.exe tools/rw330.py 398=0      # 关机

⚠ **别用 `[570]`** —— 那个名字叫 MCSET，但实际是「选哪台压缩机」（手动化霜/点检用，
    工具里标的是 "当前外机压缩机选择 1=1#压机 2=2#压机"），写它不会开关机。
    （第一版就是踩了这个，白跑 1500 秒。）

⚠ 结果文件**每次记录就增量落盘一次**，中途被杀也不丢。

跑法： python.exe tools/probe_330_startup_seq.py 900
      python.exe tools/probe_330_startup_seq.py 1500 --cycle --hold=40
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1
OUT = pathlib.Path(__file__).resolve().parent / "probe_330_startup_seq.txt"

# DisinfectStepDisp 取值 -> 说明
# 开机侧 = stepBase + {1,2,5}，stepBase = 110 制冷 / 120 制热 / 130 通风 / 100 其他
#   （UserAction.c:1370 stepBase+1、:1384 stepBase+2、:1397 stepBase+5）
_OPSUB = {1: "阶段1 风阀全开(等 valveDelay)", 2: "阶段2 链式启动风机(排→送→回)",
          5: "阶段5 等压差持续闭合 10s"}
_OPBASE = {100: "其他", 110: "制冷", 120: "制热", 130: "通风"}
STEP = {
    201: "加湿器关闭后等 30s", 202: "再热/预热关闭 + 等外机停稳",
    203: "逆序停风机(送→30s→回→30s→排)", 205: "风机停完后再等 30s",
    206: "风阀关闭完成",
    240: "[故障] 急停卸载（IndoorEmergencyStopLoads，UserAction.c:2383）",
}


# ⚠ 消排毒模式（[236]∈{3,4,5}）走的是**另一条路径** IndoorDisinfectExhaustAction，
#   它在末尾 `DisinfectStepDisp = step`（UserAction.c:1851）把**内部步号 1~6** 原样写出来，
#   和开关机那套 110/120/130+{1,2,5} 完全不是一回事。
_DIS_STEP = {
    1: "开阀 → 等 150s（消毒/消排毒:回风阀+送风阀；排毒:新风+送风+排风）",
    2: "开风机：消毒=开送风机等 20s ／ 排毒=按送排间隔时间轴跑到 phaseFanSequenceEnd",
    3: "消毒装置开(DisinfectY12) → 按【消毒模式运行时间】计时",
    4: "排毒计时 → 按【排毒模式运行时间】",
    5: "关送风机 → 等 30s → 回转 step1 进排毒段（消排毒的两段串接）",
    6: "收尾：按【结束后运行模式选择】逆序停风机",
    7: "全关输出前再等 30s",
    # step 8 不会出现在显示里 —— 它是 else 分支，写完 `step = 0` 才执行 :1851 的赋值
}

# ⚠ 210/211/212/214 **不是掉线**，而是「机器原本在运行 → 先停掉原模式」的四步。
#   UserAction.c:1659 `step = (SysStep == 0) ? 1 : 10;` —— 机器已停时直接进 step 1，
#   所以这四步跑不跑，取决于切进排毒/消排毒之前机器是不是运行态。
#   语义与 SysBoardAction 的 201/202/203/205 一一对应，只是另一条代码路径。
_DIS_PRESTOP = {
    210: "[入排毒前] 关加湿器 + 恢复停机快照风阀（原模式用加湿器才等 30s）",
    211: "[入排毒前] 停再热/预热 + 清外机命令 → 等外机停稳（制热 60s / 制冷 30s / 通风跳过）",
    212: "[入排毒前] 停内机负载 + 逆序停风机",
    214: "[入排毒前] 风机停完后再等 30s → 关风阀 → SysStep=0 → 进 step 1",
}


def step_name(d):
    if d in STEP:
        return STEP[d]
    if d in _DIS_PRESTOP:
        return _DIS_PRESTOP[d]
    if d in _DIS_STEP:
        return _DIS_STEP[d]
    if 100 <= d <= 139:
        base, sub = (d // 10) * 10, d % 10
        return "%s [%s]" % (_OPSUB.get(sub, "阶段?%d" % sub), _OPBASE.get(base, "?"))
    return "?"
WM = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排风", 5: "自动消排毒"}

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


def main() -> int:
    import app as m

    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 900.0
    # --cycle：探针自己触发一轮「关机 → 开机」。
    # ⚠ 必须由本进程触发 —— 另开一个进程写 [398] 会和本进程抢 COM6（实测会把读值搞乱）。
    cycle = "--cycle" in sys.argv
    hold = 40.0          # 每个稳态至少观察这么久
    for a in sys.argv[1:]:
        if a.startswith("--hold="):
            hold = float(a.split("=", 1)[1])

    # 开跑前先自证"端口真的在" —— 否则会在 client.open() 抛异常、一行都不写就退出，
    # 而结果文件保持旧内容，看起来像"跑过了"（2026-09-20 就是这么白等一轮的）。
    import serial.tools.list_ports as _lp
    _have = [p.device for p in _lp.comports()]
    say("=== 330 §3.3 开关机序列时序探针（只读）===")
    say("端口预检：%s  %s" % (PORT, "在" if PORT in _have else "**不在**（现有：%s）" % _have))
    if PORT not in _have:
        say("✗ %s 不存在，直接退出（不空等）。" % PORT)
        OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
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

    say("模式[236]=%s  SysStep[709]=%d  OnOff[398]=%s  DisinfectStepDisp[885]=%s"
        % (WM.get(rd(236), rd(236)), rd(709), rd(398), rd(885)))
    say("风阀延时 [346]?（硬编码 150/10，无参数）  排风-送风错开 [328]=%s  送风-回风错开 [132]=%s"
        % (rd(328), rd(132)))
    say("最小/最大无关；压差开关 [453]送=%s [454]回=%s" % (rd(453), rd(454)))
    say()
    def wr(a, v):
        for _ in range(3):
            try:
                client.write_single_register(SLAVE, a, v & 0xFFFF)
                time.sleep(0.3)
                return rd(a) == v
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        return False

    if cycle:
        say("⚠ --cycle：本进程会自己写 [398] HMIOnOffCommandSet 触发一轮「关机 → 开机」。")
        say("   （必须由本进程触发 —— 另开进程写 [398] 会抢 COM6，实测会把读值搞乱。）")
    else:
        say("⚠ 开/关机请另外触发： python.exe tools/rw330.py 398=1（开） / 398=0（关）")
    say()

    prev_step, prev_sys = None, None
    seg_start = time.time()
    segs: list[tuple[float, int, int, float]] = []   # (t, sysstep, disp, 持续秒)
    t0 = time.time()
    prev_line = 0.0
    cyc, cyc_t = 0, time.time()      # 0等运行态 1已触发关机 2等关机完 3已触发开机 5完成
    while time.time() - t0 < seconds:
        now = time.time()
        ss, ds = rd(709), rd(885)
        if ss is None or ds is None:
            time.sleep(0.4); continue

        if cycle:
            if cyc == 0 and ss == 2 and (now - cyc_t) >= hold:
                ok = wr(398, 0)
                say("  >> t=%.0fs 触发【关机】[398]=0  回读%s" % (now - t0, "OK" if ok else "!! 失败")); cyc, cyc_t = 1, now
            elif cyc == 1 and ss == 0:
                say("  >> t=%.0fs 关机序列完成（SysStep=0）" % (now - t0))
                cyc, cyc_t = 2, now
            elif cyc == 2 and (now - cyc_t) >= hold:
                ok = wr(398, 1)
                say("  >> t=%.0fs 触发【开机】[398]=1  回读%s" % (now - t0, "OK" if ok else "!! 失败")); cyc, cyc_t = 3, now
            elif cyc == 3 and ss == 2:
                say("  >> t=%.0fs 开机序列完成（SysStep=2）—— 一轮结束" % (now - t0))
                cyc = 5
                segs.append((now - t0, prev_sys, prev_step, now - seg_start))
                break

        key = (ss, ds)
        if key != (prev_sys, prev_step):
            if prev_step is not None:
                segs.append((now - t0, prev_sys, prev_step, now - seg_start))
            # （风阀 DO / 风机 DO 不在 Modbus 镜像里 —— 要核动作顺序请另开
            #   tools/_read_heat_io.py 走 ST-Link 直读 output[]/DA[]）
            say("  t=%6.1fs  SysStep %s→%s   Step %s→%s  (%s)"
                % (now - t0, prev_sys, ss, prev_step, ds, step_name(ds)))
            prev_sys, prev_step, seg_start = ss, ds, now
            prev_line = now
            OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")   # 增量落盘
        time.sleep(1.0)

    say()
    say("=== 分段时长 ===")
    say("     t | SysStep | Step | 持续(s) | 说明")
    for t, ss, ds, dur in segs:
        say("  %5.0f | %7d | %4d | %7.0f | %s" % (t, ss, ds, dur, step_name(ds)))
    say()

    # 判据提示
    say("=== 对照判据（人工核对）===")
    say("  开机：阶段1(风阀全开) 应 = 有风阀 150s / 无风阀 10s；")
    say("        阶段5(压差) 应 = 压差开关闭合后 10s（未装则立即通过）；")
    say("        两阶段之间的风机链式启动 = 排风→30s→送风→30s→回风（[328]/[132] 可调）。")
    say("  关机：201→202→203→205→206；")
    say("        201 恒温恒湿时 30s；203 逆序停风机(送→30s→回→30s→排)；205 = 30s。")
    say("  ⚠ 规格书的风阀**开/关顺序**代码里是同一拍全动（无级差）；")
    say("     且规格书未给阀间延时，功能等价 —— 用户 2026-09-20 裁定不算不符合。")

    client.close()
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
