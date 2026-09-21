# -*- coding: utf-8 -*-
"""330 §3.4.2 定频压缩机**分配与轮换** —— 指令/状态对照 + 计时约束 + 加减载次序。

规格书 §3.4.2 第 2 条：
    加载：优先开【已经运行的室外机】中满足开启条件且未开启的压缩机；
          其次开【运行时间较短】的未开启室外机（外机工作时长相差在 **2 小时**内时
          按**外机序号先后**启动；同一外机优先开**运行时间较短**的压缩机）
    减载：优先关【运行时间较长】的室外机中满足关机要求的压缩机；
          同一外机中优先关**运行时间较长**的压缩机
    压缩机最小停机时间 **2 分钟**，最小开机时间 **3 分钟**，压缩机开关间隔 **30 秒**。
    化霜状态的室外机不参与加减载。

固件对应（CompAction.c）：
    OutdoorRuntimePreferCandidate() (139)  加载排序，2h 同带比较 = 7200 秒
    OutdoorRuntimePreferUnloadCandidate() (626) 减载排序
    CompTargetSelectStartComp() (893)      同机内挑压机（加载取运行时长**短**）
    CompCanUnload() (405)                  减载门槛：最小开机时间 + 非化霜
    CompMinRunStopCount() (1260)           计时累计（**注意：状态 4 化霜也算"在运行"**）

参数下标（已逐个对着 User.h 核过）：
    台数   [118] CompNumSet  [119] CompNumCur
    各外机状态  [1550+70*(N-1)+5] 压机1、+6 压机2   （PLCMonitor=1550）
    各压机精确运行秒数  [2602 + (N-1)*4 + c*2] 高字、+1 低字   （PSC316_RUNTIME_HMI_BASE）
    各外机累计运行秒数  [2670 + (N-1)*2] 高字、+1 低字         （PSC316_OUTDOOR_RUNTIME_HMI_BASE）
    单台指令/状态（要选页）  [540] ModeNumDisp → [950]/[951] 指令、[1425]/[1426] 状态
    前提   [315] CompControlModeSet 必须 ==0（==1 是环温模式，走 CompEnvLowLoad，另一套顺序）
    计时门槛  [42] MinStopTimeSet  [43] MinRunTimeSet（固件取 max(参数, 常量 120/180)）
    [214] ModuleNumSet —— 有效外机是 1 .. ModuleNumSet-1

⚠ **选页有副作用**：`[540]` 是 HMI 的"看哪台外机"选择器。本脚本只为了读 [950]/[951]
  单台指令才去写它，**结束时必须复原**（脚本会打印原值）。
⚠ 主循环**只读**，不写任何寄存器。计时判据从**状态跳变沿**测，1 秒分辨率。
⚠ 等待时间要算够（不然会误判成"没按规格书迁移"）：
  30s 开关间隔 + 45s 分布防抖（COMP_TARGET_DISTRIBUTION_DEBOUNCE_SECONDS）
  + 启动反馈超时 clamp(FanONLaySet+30, 60, 300)s + 启动失败后 300s 禁试。

跑法： python.exe tools/probe_330_comp_rotation.py 600
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1
OUT = pathlib.Path(__file__).resolve().parent / "probe_330_comp_rotation.txt"

PLC_MONITOR = 1550
UNIT_STEP = 70
RUNSEC_BASE = 2602          # 每机 4 字：c0 高/低, c1 高/低
RUNSEC_WORDS = 4
OUTSEC_BASE = 2670          # 每机 2 字
OUTSEC_WORDS = 2
SPEC_MIN_STOP, SPEC_MIN_RUN, SPEC_GAP = 120, 180, 30

# 固件口径：状态 2/3/4 都算"在运行"（CompMinRunStopCount 第 1282 行）
RUNNING = (2, 3, 4)
CS = {0: "停止", 1: "故障", 2: "制冷", 3: "制热", 4: "化霜", 5: "禁用"}

LINES: list[str] = []


def say(s: str = "") -> None:
    """双写：UTF-8 .txt 是交付物；控制台是 GBK，打印失败不能影响采样。"""
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
    seconds = float(nums[0]) if nums else 600.0
    # --sweep=lo,hi  每 --every=N 秒在 lo/hi 之间翻转 [495]（NTC0 校准偏移），
    # 逼出加卸载循环；不然空闲时会一台跳变都看不到。
    sw_lo = sw_hi = None
    sw_every = 200.0
    for a in sys.argv[1:]:
        if a.startswith("--sweep="):
            lo, hi = a.split("=", 1)[1].split(",")
            sw_lo, sw_hi = int(lo), int(hi)
        elif a.startswith("--every="):
            sw_every = float(a.split("=", 1)[1])
    sweep = sw_lo is not None and sw_hi is not None

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    def rd(addr):
        for _ in range(3):
            try:
                return s16(client.read_holding_registers(SLAVE, addr, 1)[0])
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        return None

    def rd32(hi_addr):
        hi, lo = rd(hi_addr), rd(hi_addr + 1)
        if hi is None or lo is None:
            return None
        return ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)

    # ---- 前提 ----
    cfg = {a: rd(a) for a in (315, 214, 388, 42, 43, 118, 119, 540, 709, 495)}
    if None in cfg.values():
        say("✗ 开场读失败"); client.close()
        OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8"); return 1

    # ⚠ 走哪条路不是只看 [315]：环温模式的真正条件是
    #   (CompControlModeSet==1) && IndoorIsFreshAirOnlySystem()
    #   （= 回风机无、回风阀无、混风阀无）。所以用固件自己的 [872] IndoorCtrlModeDisp 判定：
    #   0=PID 路径（§3.4.2 适用）、1=环温路径（走 CompEnvLowLoad，另一套顺序）。
    ctrl = rd(872)
    say("=== 330 §3.4.2 压缩机分配与轮换 ===")
    say("控制方式[315]=%d   回风机[330]=%d 回风阀[337]=%d 混风阀[381]=%d"
        % (cfg[315], rd(330), rd(337), rd(381)))
    say("⇒ 固件实际路径 [872] IndoorCtrlModeDisp=%s" % ctrl)
    say("外机台数[214]=%d ⇒ 有效外机 1..%d" % (cfg[214], cfg[214] - 1))
    say("最小停机[42]=%ds（固件取 max(参数, 120)）  最小开机[43]=%ds（取 max(参数, 180)）"
        % (cfg[42], cfg[43]))
    say("台数[118]目标=%d  [119]当前=%d   SysStep[709]=%d" % (cfg[118], cfg[119], cfg[709]))
    say()
    if ctrl == 1:
        say("⚠ 走的是环温路径 CompEnvLowLoad（反序号扫描、不做运行时长排序），")
        say("  与 §3.4.2 的 PID 路径不同 —— 下面的次序判据不适用，只报数据。")
    say("【复原清单】本脚本会写 [540] ModeNumDisp（原值 %d）" % cfg[540])
    if sweep:
        say("                  + [495] NTC0 校准偏移（原值 %d，结束会复原）" % cfg[495])
    say()

    units = list(range(1, min(cfg[214], 4)))
    # ⚠ [540] 的可写范围受 [388] OutdoorUnitNumSet 限制（modbus.c 白名单），不是 [214]
    sel_units = list(range(1, min(cfg[214], cfg[388], 4) + 1))
    if len(sel_units) < len(units):
        say("⚠ [388] OutdoorUnitNumSet=%d 只允许选页到外机 %d，选页那节会少几台"
            % (cfg[388], sel_units[-1] if sel_units else 0))
        say()

    # ---- 指令 vs 状态 对照表（要选页，样本一次性）----
    say("--- 指令 vs 状态 对照表（[950]/[951] = 330 的指令；[1425]/[1426] = 316 回报的状态）---")
    say("  外机 | 压机1 指令/状态 | 压机2 指令/状态 | 说明")
    for u in sel_units:
        if rd(540) != u:
            client.write_single_register(SLAVE, 540, u)
            time.sleep(0.4)
        c1, c2 = rd(950), rd(951)
        st1, st2 = rd(1425), rd(1426)
        note = ""
        if c1 is not None and st1 is not None:
            if (c1 == 1) != (st1 in RUNNING):
                note = "⚠ 指令与状态不一致"
        say("  %4d |      %s / %-4s |      %s / %-4s | %s"
            % (u, c1, CS.get(st1, st1), c2, CS.get(st2, st2), note))
    client.write_single_register(SLAVE, 540, cfg[540] & 0xFFFF)   # 复原选页
    time.sleep(0.3)
    say("  （[540] 已复原为 %d）" % cfg[540])
    say()

    # ---- 主循环：只读，从状态跳变沿测计时 ----
    say("已开始采样 %.0f 秒（逐秒，只记跳变）…" % seconds)
    say()
    say("     t | 目标 当前 | 外机1 压机1/2 | 外机2 压机1/2 | 事件")
    say("       |           |   状态 运行秒 |   状态 运行秒 |")

    state: dict[tuple[int, int], int] = {}
    tsince: dict[tuple[int, int], float] = {}      # 该状态持续了多久（起点时间）
    last_cmd_change = 0.0
    events: list[str] = []
    t0 = time.time()
    prev_line = 0.0
    sw_next = t0 + sw_every
    sw_hi_now = False
    while time.time() - t0 < seconds:
        now = time.time()
        if sweep and now >= sw_next:
            sw_hi_now = not sw_hi_now
            client.write_single_register(SLAVE, 495, (sw_hi if sw_hi_now else sw_lo) & 0xFFFF)
            say("  ── 注入翻转：[495] = %d（%s）"
                % (sw_hi if sw_hi_now else sw_lo, "加载" if sw_hi_now else "减载"))
            sw_next = now + sw_every
        nset, ncur = rd(118), rd(119)
        if nset is None or ncur is None:
            time.sleep(0.5); continue
        cur: dict[tuple[int, int], int] = {}
        secs: dict[tuple[int, int], int] = {}
        for u in units:
            for c in (0, 1):
                st = rd(PLC_MONITOR + (u - 1) * UNIT_STEP + 5 + c)
                rs = rd32(RUNSEC_BASE + (u - 1) * RUNSEC_WORDS + c * 2)
                if st is None:
                    continue
                cur[(u, c)] = st
                secs[(u, c)] = rs if rs is not None else -1

        ev = ""
        for k, st in cur.items():
            old = state.get(k)
            if old is None:
                state[k] = st
                tsince[k] = now
                continue
            if st == old:
                continue
            # 跳变
            held = now - tsince.get(k, now)
            was_run = old in RUNNING
            now_run = st in RUNNING
            tag = ""
            if was_run and not now_run:
                tag = "停机(运行了%.0fs)" % held
                if held < max(cfg[43], SPEC_MIN_RUN):
                    tag += " ⚠ 短于最小开机 %ds" % max(cfg[43], SPEC_MIN_RUN)
            elif (not was_run) and now_run:
                tag = "启动(停了%.0fs)" % held
                if held < max(cfg[42], SPEC_MIN_STOP):
                    tag += " ⚠ 短于最小停机 %ds" % max(cfg[42], SPEC_MIN_STOP)
            gap = now - last_cmd_change
            if gap < SPEC_GAP:
                tag += " ⚠ 距上次开关仅 %.0fs < %ds" % (gap, SPEC_GAP)
            last_cmd_change = now
            ev = "外机%d压机%d %s→%s %s" % (k[0], k[1] + 1, CS.get(old, old), CS.get(st, st), tag)
            events.append("t=%6.0fs  %s" % (now - t0, ev))
            state[k] = st
            tsince[k] = now

        if ev or (now - prev_line >= 20):
            cells = []
            for u in units:
                cells.append(" ".join("%s/%-5s" % (CS.get(cur.get((u, c)), "?"), secs.get((u, c), "?"))
                                      for c in (0, 1)))
            say("  %5.0f | %4d %4d | %s | %s"
                % (now - t0, nset, ncur, cells[0] if len(cells) > 0 else "",
                   cells[1] if len(cells) > 1 else ""))
            if ev:
                say("        └─ %s" % ev)
            prev_line = now
        time.sleep(0.9)

    say()
    say("--- 跳变事件汇总（%d 条）---" % len(events))
    for e in events:
        say("  " + e)
    say()
    n_bad = sum(1 for e in events if "⚠" in e)
    say("计时判据：%s（%d 条跳变里 %d 条越界）"
        % ("全部满足" if n_bad == 0 else "有 %d 条越界" % n_bad, len(events), n_bad))
    say()
    say("【次序判据（人工核对）】加载应优先开已运行外机的未开压机 → 再运行时长短的未开外机")
    say("  （2h 同带按外机序号小）→ 同机内运行时长**短**的压机；")
    say("  减载应优先关运行时长长的外机 → 同机内运行时长**长**的压机。")
    say("  ⚠ 固件两处规格书未定义：加载平局取序号**小**(CompAction.c:152)，")
    say("    减载平局取序号**大**(:638)；且减载侧**没有 2 小时容差**，是严格比大小(:636)。")
    if sweep:
        client.write_single_register(SLAVE, 495, cfg[495] & 0xFFFF)
        time.sleep(0.4)
        say()
        say("已复原 [495] = %d（NTC0 校准偏移原值）" % cfg[495])

    client.close()
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
