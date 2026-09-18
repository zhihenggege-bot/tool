"""盯 **330 内机**的电子膨胀阀（ST-Link 插 330 时用）。

规格书（用户 2026-09-18 提供）：
    制冷运行时：**室外机**电子膨胀阀处于关闭状态，**室内机**电子膨胀阀主要根据吸气过热度控制，
                初始步数为【电子膨胀阀起始开度】
    热泵制热：  **室内机**电子膨胀阀处于关闭状态，**室外机**电子膨胀阀主要根据吸气过热度控制，
                初始步数为【电子膨胀阀起始开度】
    化霜运行时：**室内机**电子膨胀阀开度为【化霜时电子膨胀阀开度】(350)，
                **室外机**电子膨胀阀处于关闭状态
    电子膨胀阀关闭时，以 **20 步/秒** 速度关闭；关闭步数 = 当前步数 + 20

参数地址（330，EEVPARAMETER = 10）：
    [10]  MotorTotalPulseSet  总脉冲        规格 500
    [11]  EEVCloseMinSizeSet  最小开度      48
    [12]  EEVOpenMaxSizeSet   最大开度      规格 500
    [21]  DefrostEXVOpenSizeSet 化霜时开度（**派生量**，被 EEVSpecParamBridge 每周期覆写）
    [372] DefrostEEVStepSet     化霜时开度（**HMI 真正配的**，= INDOOR_SPEC_BASE(315)+57）
    [411] EEVStartStepSet       电子膨胀阀起始开度
    [1145..1152] EEV1..8 NewAddValue  目标步数
    [1153..1160] EEV1..8 OldAddValue  当前步数

⚠ 化霜开度被钳的根因（eevCTRL.c:589）：
    EEVSpecMaxStep() = clamp(EEVOpenMaxSizeSet, 200, clamp(MotorTotalPulseSet, 200, 500))
    台面 MotorTotalPulseSet = 50 -> 被下限抬到 200 -> [21] = clamp(350,100,200) = 200

只读，attach 模式。

跑法：
    python.exe tools/probe_330_eev.py --status
    python.exe tools/probe_330_eev.py 900
"""

from __future__ import annotations

import pathlib
import sys
import time

TARGET = "stm32f407ze"
PARAM_BASE = 0x200030C8
A_UNITREAD = 0x200080C8
R_STEP = 196
R_COMPSTATUS = 98

NEW_BASE = 1145                  # EEV1..8 NewAddValue
OLD_BASE = 1153                  # EEV1..8 OldAddValue
NEEV = 8

P_SHOW = [
    (10, "MotorTotalPulseSet 总脉冲", 1),
    (11, "EEVCloseMinSizeSet 最小开度", 1),
    (12, "EEVOpenMaxSizeSet 最大开度", 1),
    (21, "DefrostEXVOpenSizeSet 化霜开度(派生)", 1),
    (372, "DefrostEEVStepSet 化霜开度(HMI真配)", 1),
    (411, "EEVStartStepSet 起始开度", 1),
]
COMPSTATUS = {0: "停", 1: "故障", 2: "制冷", 3: "制热", 4: "除霜", 5: "禁用"}

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_330_eev.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    status_only = "--status" in sys.argv
    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 600.0

    session = ConnectHelper.session_with_chosen_probe(
        target_override=TARGET, options={"frequency": 1000000, "connect_mode": "attach"})
    if session is None:
        say("!! 没找到 ST-Link")
        write()
        return 1
    session.open()
    tgt = session.target
    if tgt.get_state() == tgt.State.HALTED:
        say("!! 进入时 HALTED —— 已 resume")
        tgt.resume()

    def r16m(a):
        b = tgt.read_memory_block8(a, 2)
        return b[0] | (b[1] << 8)

    def ps(i):
        b = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        v = b[0] | (b[1] << 8)
        return v - 0x10000 if v & 0x8000 else v

    def snap():
        new = [ps(NEW_BASE + i) for i in range(NEEV)]
        old = [ps(OLD_BASE + i) for i in range(NEEV)]
        cs = {}
        for u in (1, 2):
            cs[u] = [r16m(A_UNITREAD + u * R_STEP + R_COMPSTATUS + 2 * i) for i in range(2)]
        return new, old, cs

    def header():
        say("=== 330 电子膨胀阀探针 ===")
        for idx, nm, _ in P_SHOW:
            say("  [%3d] %-34s = %d" % (idx, nm, ps(idx)))
        mtp, omx = ps(10), ps(12)
        mx = clamp(omx, 200, clamp(mtp, 200, 500))
        say(f"  => EEVSpecMaxStep() = clamp([12]={omx},200,clamp([10]={mtp},200,500)) = **{mx}**")
        say(f"  => 化霜开度实际会取 clamp([372]={ps(372)},100,{mx}) = "
            f"**{clamp(ps(372), 100, mx)}**   （规格要求 {ps(372)}）")
        say()

    header()
    new, old, cs = snap()
    say("--- 当前 EEV 步数 ---")
    for i in range(NEEV):
        if new[i] or old[i]:
            say("  EEV%d: 目标[%d]=%4d   当前[%d]=%4d" % (i + 1, NEW_BASE + i, new[i],
                                                          OLD_BASE + i, old[i]))
    say("  外机 CompStatus: " + "  ".join(
        "外机%d=%s" % (u, [COMPSTATUS.get(x, x) for x in cs[u]]) for u in (1, 2)))

    if status_only:
        if tgt.get_state() == tgt.State.HALTED:
            say("!! 结束 HALTED —— resume")
            tgt.resume()
        session.close()
        write()
        return 0

    say()
    say("=== 10Hz 采样（只记变化）===")
    say("  t | 外机1 | 外机2 | EEV1 目标/当前 | EEV2 目标/当前 | ...")
    prev = None
    t0 = time.time()
    while time.time() - t0 < seconds:
        el = time.time() - t0
        if tgt.get_state() == tgt.State.HALTED:
            say(f"  [{el:6.1f}] !! HALTED —— resume")
            tgt.resume()
        try:
            new, old, cs = snap()
            cur = (tuple(new), tuple(old), tuple(tuple(cs[u]) for u in (1, 2)))
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:6.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue
        if cur != prev:
            parts = ["%6.1f" % el,
                     "%s" % [COMPSTATUS.get(x, x) for x in cs[1]],
                     "%s" % [COMPSTATUS.get(x, x) for x in cs[2]]]
            for i in range(NEEV):
                if new[i] or old[i]:
                    parts.append("EEV%d %d/%d" % (i + 1, new[i], old[i]))
            say("  ".join(parts))
            prev = cur
        time.sleep(0.1)

    if tgt.get_state() == tgt.State.HALTED:
        say("!! 结束 HALTED —— resume")
        tgt.resume()
    say(f"结束 state={tgt.get_state().name}")
    session.close()
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
