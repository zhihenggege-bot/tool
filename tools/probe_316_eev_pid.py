"""316 室外 EEV **动态记录**：每一拍把规格书的量全打出来，并当场验算 PID。

规格书 3.9（制冷：室内 EEV 受控 / 室外关闭；热泵制热：室内关闭 / 室外 EEV 受控）：

    吸气过热度 = 吸气温度 − 蒸发温度，蒸发温度 = 吸气压力对应的饱和温度
    步数 = KP×[E(K)−E(K−1) + TP/TI×E(K) + TD/TP×(E(K)−2E(K−1)+E(K−2))]
           限幅 ±【每周期加减最大步数】；|过热度−Y| ≤ YD/2 → 不动作
    A: 蒸发温度>12.0C 且 step≥0 → 固定 −5 步/周期
    B: 蒸发温度 10.0~12.0C 且 step≥0 → 不动作
    C: 其余 → 按过热度

本探针读**固件自己的** EEVSpecErrHist[0][0..2]（E(K)/E(K-1)/E(K-2)），
在 PC 侧用规格书公式重算一遍，和固件实际走出来的步数对比 —— 验证的是实现，不是纸面。

地址（fromelf -s 取自 PSC316RK-V12-20250327.axf）：
    AI                0x20001172  int16[14]   -> AI[11]=吸气温度1(AI+22), AI[12]=吸气温度2(AI+24)
    EEVSpecErrHist    0x20002778  int32[2][3] -> [i][0]=E(K) [i][1]=E(K-1) [i][2]=E(K-2)
    EEVSpecResidualMilli 0x20002790 int64[2]
    Filter_A          0x20000de6  int16[4]
    MainOverHeat1Disp = Parameter[PLCREADPara+17] = Parameter[1437]
    蒸发温度 = AI[11] − Parameter[1437]     （由 MainOverHeat1Disp 的定义反推）

只读，attach 模式（绝不停核）。
跑法： python.exe tools/probe_316_eev_pid.py 900
"""

from __future__ import annotations

import pathlib
import sys
import time

PARAM_BASE = 0x2000164A
A_AI = 0x20001172          # int16 AI[14]
A_ERRHIST = 0x20002778     # int32 EEVSpecErrHist[2][3]
A_RESID = 0x20002790       # int64 EEVSpecResidualMilli[2]
A_COMP = 0x20000DD4
A_FOUR = 0x20000DD9
A_FAN = 0x20000DDE
A_DEFSTATE = 0x20000DF0

# ---- 316 室外 EEV 参数块（User.h:546-554）----
P_WMODE = 1                # UserWorkModeSet
P_Y = 198                  # EEVSuperHeatTargetSet    0.1C
P_KP = 199                 # EEVPidKpSet
P_PIDEN = 200              # EEVSpecPidEnableSet
P_START = 201              # EEVStartStepSet
P_YD = 202                 # EEVSuperHeatDeadSet      0.1C
P_TP = 203                 # EEVPidScanTimeSet        s
P_TI = 204                 # EEVPidPidTiSet           s
P_TD = 205                 # EEVPidTdSet              s
P_LIMIT = 206              # EEVStepLimitSet

P_NEW, P_OLD, P_RUN = 805, 809, 813
P_OVERHEAT1 = 1437         # MainOverHeat1Disp

WM = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排风", 5: "自动"}

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_316_eev_pid.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 900.0

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"})
    if session is None:
        say("!! 没找到 ST-Link")
        write()
        return 1
    session.open()
    tgt = session.target
    if tgt.get_state() == tgt.State.HALTED:
        say("!! 进入时 HALTED —— 已 resume")
        tgt.resume()

    def r8(a):
        return tgt.read_memory_block8(a, 1)[0]

    def r8n(a, n):
        return list(tgt.read_memory_block8(a, n))

    def r16(a):
        b = tgt.read_memory_block8(a, 2)
        return b[0] | (b[1] << 8)

    def ps(i):
        v = r16(PARAM_BASE + i * 2)
        return v - 0x10000 if v & 0x8000 else v

    def r32s(a):
        b = tgt.read_memory_block8(a, 4)
        v = b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
        return v - 0x100000000 if v & 0x80000000 else v

    def r64s(a):
        lo = r32s(a) & 0xFFFFFFFF
        hi = r32s(a + 4)
        v = (hi << 32) | lo
        return v

    say("=== 316 室外 EEV 动态记录（规格书 3.9 验算）===")
    say("版本 = %s   机型[165]=%d 风机[166]=%d  工作模式=%s"
        % ([ps(1000 + i) for i in range(6)], ps(165), ps(166),
           WM.get(ps(P_WMODE), ps(P_WMODE))))
    say("参数: Y=%.1fC  YD=%.1fC  KP=%d  TP=%ds  TI=%ds  TD=%ds  起始开度=%d  "
        "每周期最大=%d  PID使能=%d"
        % (ps(P_Y) / 10.0, ps(P_YD) / 10.0, ps(P_KP), ps(P_TP), ps(P_TI), ps(P_TD),
           ps(P_START), ps(P_LIMIT), ps(P_PIDEN)))
    say()
    say("  规格书: 步数 = KP×[E0−E1 + TP/TI×E0 + TD/TP×(E0−2E1+E2)]  (E 单位 0.1C)")
    say("  ⚠ 固件内部多除一个 10 —— 那是 0.1C→C 的单位补偿，PC 侧重算时同样除 10 才可比")
    say()
    say("   t | WMd | 吸气T 蒸发T 过热 Y | E0 E1 E2 | 算式 分支后 | EEV1 目标/当前 | 累计开 累计关 | 备注")
    say("  （Δ 只在实际变化时打；「算式」= 规格书公式算出，「分支后」= 经 A/B/C/死区/限幅 之后）")
    prev = None
    prev_new = None
    prev_mode = None
    acc_open = acc_close = 0
    t0 = time.time()
    nxt_wd = 0.0
    while time.time() - t0 < seconds:
        el = time.time() - t0
        if el >= nxt_wd:
            nxt_wd = el + 10.0
            if tgt.get_state() == tgt.State.HALTED:
                say(f"  [{el:6.1f}] !! HALTED —— resume")
                tgt.resume()
        try:
            wm = ps(P_WMODE)
            suc = r16(A_AI + 11 * 2)          # 吸气温度1, 0.1C
            over = ps(P_OVERHEAT1)            # 过热度1, 0.1C
            eva = suc - over                  # 蒸发温度 = 吸气 − 过热度
            y = ps(P_Y)
            e0 = r32s(A_ERRHIST + 0)
            e1 = r32s(A_ERRHIST + 4)
            e2 = r32s(A_ERRHIST + 8)
            kp, tp, ti, td = ps(P_KP), ps(P_TP), ps(P_TI), ps(P_TD)
            limit, yd = ps(P_LIMIT), ps(P_YD)
            new = ps(P_NEW)
            old = ps(P_OLD)
            run = ps(P_RUN)
            comp = r8n(A_COMP, 2)
            four = r8n(A_FOUR, 2)
            fan = r8n(A_FAN, 2)
            dst = r8(A_DEFSTATE)
            resid = r64s(A_RESID + 0)
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:6.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue

        # ---- PC 侧按规格书公式重算（含固件那个 0.1C 补偿）----
        # ⚠ 必须用 C 的**向零截断**除法，不能用 Python 的 //（向下取整）——
        #   否则负误差会差 1（-41.05 会被算成 -42）。
        def tdiv(a, b):
            q = abs(a) // abs(b)
            return q if (a >= 0) == (b >= 0) else -q

        num = (e0 - e1) * ti * tp + tp * tp * e0 + td * ti * (e0 - 2 * e1 + e2)
        den = 10 * ti * tp
        calc = tdiv(tdiv(kp * num * 1000, den) + resid, 1000) if den else 0
        # A/B
        note = ""
        if eva > 120 and calc >= 0:
            note, clampd = "A(蒸发>12→-5)", -5
        elif 100 <= eva <= 120 and calc >= 0:
            note, clampd = "B(10~12→0)", 0
        elif -yd // 2 <= (e0) <= yd // 2:
            note, clampd = "死区", 0
        else:
            clampd = max(-limit, min(limit, calc))
            note = "C(限幅)" if clampd != calc else "C"

        act = ""
        if prev_new is not None and new != prev_new:
            d = new - prev_new
            if d > 0:
                acc_open += d
            else:
                acc_close += -d
            act = f"** Δ={d:+d} **"
        if prev_mode is not None and wm != prev_mode:
            act += f"  <<< 模式 {WM.get(prev_mode)} -> {WM.get(wm)} >>>"
        prev_new = new
        prev_mode = wm

        key = (wm, suc, over, e0, e1, e2, new, old, run, tuple(comp), tuple(four),
               tuple(fan), dst)
        if key != prev or act:
            say("  %5.0f | %-4s | %5.1f %5.1f %5.1f %4.1f | %4d %4d %4d | %4d %4d |"
                " %4d/%-4d %-14s | %5d %5d | %s"
                % (el, WM.get(wm, wm), suc / 10.0, eva / 10.0, over / 10.0, y / 10.0,
                   e0, e1, e2, calc, clampd, new, old, act, acc_open, acc_close, note))
            prev = key
        time.sleep(0.1)

    if tgt.get_state() == tgt.State.HALTED:
        say("!! 结束 HALTED —— resume")
        tgt.resume()
    say(f"结束 state={tgt.get_state().name}   累计 开{acc_open} 步 / 关{acc_close} 步")
    session.close()
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
