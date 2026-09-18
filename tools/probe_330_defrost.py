"""盯 **330 内机**的化霜排他性 + 辅热 + 室内 EEV（ST-Link 插 330 时用）。

symbol 从 `Project/Obj/PSC330RK-V10.axf` 用 fromelf 取（330 的 .map 只有 Memory Map，
**没有符号表**，不能像 316 那样从 map 拿地址）。结构体大小和符号大小互相印证：
    UnitWriteInfo = 120 字节  (UnitWriteStatus 0x870 = 2160 / 18 = 120) ✓
    UnitReadInfo  = 196 字节  (UnitReadStatus  0xdc8 = 3528 / 18 = 196) ✓

验证目标：
  ① 排他性（规格 4.4 正文「同时只能有一个室外机在化霜」）
     PSC316DefrostOwner 是**单个静态字节** —— 天然只能有一个 owner。
     再看 UnitWriteStatus[u].DefrostSignal 是否只对 owner 为 1。
  ② 辅热（规格：收到化霜开始指令后辅热全开、结束后全关）
     Heat1Y00/Heat2Y01/Heat3Y02 = output[0..2]
     IndoorHeatAnalogDemand（AO 模式下的模拟量需求）/ IndoorHeatAnalogMode
     ReheatPidStateDisp(=Parameter[942])，化霜时应为 REHEAT_PID_STATE_DEFROST
  ③ 室内 EEV：DefrostEXVOpenSizeSet(=Parameter[21]) 与 DefrostEEVStepSet(=Parameter[372])
     —— 注意 [21] 每周期被 [372] 覆盖，HMI 真正配的是 [372]

只读，attach 模式（绝不停核）。

跑法：
    python.exe tools/probe_330_defrost.py --status
    python.exe tools/probe_330_defrost.py 1800
    python.exe tools/probe_330_defrost.py 1800 5
"""

from __future__ import annotations

import pathlib
import sys
import time

TARGET = "stm32f407ze"           # 330 是 F407
PARAM_BASE = 0x200030C8          # int16_t Parameter[]
A_DEFROST_OWNER = 0x20000ECE     # unsigned char PSC316DefrostOwner  <- 排他性核心
A_UNITWRITE = 0x20007858         # UnitWriteInfo UnitWriteStatus[18]
A_UNITREAD = 0x200080C8          # UnitReadInfo  UnitReadStatus[18]
A_OUTPUT = 0x20001364            # unsigned short output[8] = Y00..Y07
A_HEAT_ANALOG_DEMAND = 0x20000D18   # int  IndoorHeatAnalogDemand
A_HEAT_ANALOG_MODE = 0x20000D20     # uchar IndoorHeatAnalogMode

W_STEP = 120                     # sizeof(UnitWriteInfo)
R_STEP = 196                     # sizeof(UnitReadInfo)
W_DEFSIGNAL = 16                 # int16_t DefrostSignal[4]
R_COMPSTATUS = 98                # int16_t CompStatus[4]
R_CANDEFROST = 106               # int16_t CanDefrost[4]

NUNITS = 6                       # 台面上最多看 6 台

P = {
    "ReheatEnableSet": 127,
    "HeatModeSet": 128,          # 0无 1热泵制热 2AO 3=1:2 4=1:2:4 5SCR
    "HeatReheatShareSet": 129,
    "ReheatModeSet": 315 + 17,   # 332
    "PreheatModeSet": 315 + 18,  # 333
    "ReheatPidStateDisp": 942,
    "DefrostEXVOpenSizeSet": 21,
    "DefrostEEVStepSet": 315 + 57,   # 372
}
HEAT_MODE = {0: "无", 1: "热泵制热", 2: "AO", 3: "1:2", 4: "1:2:4", 5: "SCR"}
OUT_MODE = {0: "无", 1: "AO", 2: "1:2", 3: "1:2:4", 4: "SCR"}
COMPSTATUS = {0: "停", 1: "故障", 2: "制冷", 3: "制热", 4: "除霜", 5: "禁用"}

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_330_defrost.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    status_only = "--status" in sys.argv
    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 600.0
    every = float(nums[1]) if len(nums) > 1 else 10.0

    session = ConnectHelper.session_with_chosen_probe(
        target_override=TARGET,
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
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

    def r16m(a):
        b = tgt.read_memory_block8(a, 2)
        return b[0] | (b[1] << 8)

    def r32(a):
        b = tgt.read_memory_block8(a, 4)
        return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)

    def ps(i):
        b = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        v = b[0] | (b[1] << 8)
        return v - 0x10000 if v & 0x8000 else v

    def snap():
        owner = r8(A_DEFROST_OWNER)
        units = []
        for u in range(1, NUNITS + 1):
            cs = [r16m(A_UNITREAD + u * R_STEP + R_COMPSTATUS + 2 * i) for i in range(2)]
            cd = [r16m(A_UNITREAD + u * R_STEP + R_CANDEFROST + 2 * i) for i in range(2)]
            ds = [r16m(A_UNITWRITE + u * W_STEP + W_DEFSIGNAL + 2 * i) for i in range(2)]
            units.append((cs, cd, ds))
        out = [r16m(A_OUTPUT + 2 * i) for i in range(3)]
        return owner, units, out, r32(A_HEAT_ANALOG_DEMAND), r8(A_HEAT_ANALOG_MODE)

    owner, units, out, had, ham = snap()
    say("=== 330 化霜/辅热 探针 ===")
    say(f"版本 Parameter[0..5] = {[ps(i) for i in range(6)]}")
    say()
    say("--- 加热配置 ---")
    say(f"  再热是否启用[127]={ps(127)}  制热方式[128]={ps(128)}"
        f" ({HEAT_MODE.get(ps(128), '?')})  共用[129]={ps(129)}")
    say(f"  再热/辅热方式[{P['ReheatModeSet']}]={ps(P['ReheatModeSet'])}"
        f" ({OUT_MODE.get(ps(P['ReheatModeSet']), '?')})"
        f"  预热输出方式[{P['PreheatModeSet']}]={ps(P['PreheatModeSet'])}")
    say(f"  化霜阀开度 [21](派生)={ps(21)}   [{P['DefrostEEVStepSet']}](HMI真配)={ps(P['DefrostEEVStepSet'])}")
    say()
    say("--- 化霜排他性 ---")
    say(f"  **PSC316DefrostOwner = {owner}**   (0=无人在化霜；单字节 -> 天然唯一)")
    for u in range(1, NUNITS + 1):
        cs, cd, ds = units[u - 1]
        tag = "  <== owner" if u == owner else ""
        say("  外机%d: CompStatus=%s  CanDefrost=%s  DefrostSignal=%s%s"
            % (u, [COMPSTATUS.get(x, x) for x in cs], cd, ds, tag))
    say()
    say(f"--- 辅热 ---")
    say(f"  output[0..2] = {out}  (Heat1Y00/Heat2Y01/Heat3Y02)")
    say(f"  IndoorHeatAnalogDemand = {had}   IndoorHeatAnalogMode = {ham}"
        f" ({OUT_MODE.get(ham, '?')})")
    say(f"  ReheatPidStateDisp[942] = {ps(942)}")

    if status_only:
        if tgt.get_state() == tgt.State.HALTED:
            say("!! 结束 HALTED —— resume")
            tgt.resume()
        session.close()
        write()
        return 0

    say()
    say("=== 10Hz 采样（只记变化）===")
    say("  t | Owner | 外机1 CS/CD/DS | 外机2 CS/CD/DS | 外机3 CS/CD/DS |"
        " HeatY00/01/02 | AODemand Mode | PIDstate")
    prev = None
    t0 = time.time()
    nxt_wd = 0.0
    nxt_force = 0.0
    while time.time() - t0 < seconds:
        el = time.time() - t0
        if el >= nxt_wd:
            nxt_wd = el + 10.0
            if tgt.get_state() == tgt.State.HALTED:
                say(f"  [{el:6.1f}] !! HALTED —— resume")
                tgt.resume()
        force = el >= nxt_force
        if force:
            nxt_force = el + every
        try:
            owner, units, out, had, ham = snap()
            cur = (owner, tuple(tuple(x) for x in units[:4]), tuple(out), had, ham, ps(942))
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:6.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue
        if cur != prev or force:
            parts = ["%6.0f" % el, "%5d" % cur[0]]
            for u in range(4):
                cs, cd, ds = cur[1][u]
                parts.append("%s/%s/%s" % (cs, cd, ds))
            parts.append("%d/%d/%d" % cur[2])
            parts.append("%5d %d" % (cur[3], cur[4]))
            parts.append("%d" % cur[5])
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
