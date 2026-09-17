"""同时读两路：ST-Link 读 316（外机1）内部量 + COM6 读 330 寄存器。

用途：查「热泵制热时冷凝风机为什么只开一台」。

316 侧要读的量大多是 `static`/宏，地址来自当前固件的 .axf 符号表
（`OBJ/PSC316RK-V12-20250327.axf`）与 `User.h` 的宏定义换算：

    Parameter 基址 = 0x2000164A        （.axf 符号表，与调试记录 4.3 一致）
    地址 = 基址 + 下标*2               （int16_t Parameter[]）

跑法：
    python.exe tools/read_316_fan_state.py [采样秒数] [COM口]
默认采样 30 秒、COM6。输出写 UTF-8 文件再读（GBK 控制台会炸）。
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PARAM_BASE = 0x2000164A          # int16_t Parameter[ParameterSize]

LINES: list[str] = []


def line(s: str = "") -> None:
    LINES.append(s)


def p_addr(index: int) -> int:
    """Parameter[index] 的绝对地址。"""
    return PARAM_BASE + index * 2


# 符号表中的绝对地址（已核对 .axf）
ABS = {
    "AI": 0x20001172,                       # volatile uint16_t AI[14]
    "SensorStatus": 0x2000114C,             # uint8_t SensorStatus[14]
    "OUTDOOR_SPEC": None,
}
# 宏 → Parameter 下标
IDX = {
    "UserWorkModeSet": 1,                   # Parameter[1]
    "OutdoorFanTypeSet": 165 + 1,           # Parameter[OUTDOOR_SPEC+1]，OUTDOOR_SPEC=165
    "FanOpenSet": 872,                      # 单速/定速风机命令
    "FanOpenSet2": 874,                     # 双速风机命令
    "FanSpeedCtrl": 1420 + 43,              # Parameter[PLCREADPara+43]，PLCREADPara=1420
    "EnviTempAI0Disp": 1420 + 2,            # ← 316 判断风机用的环温
}


def hexdump_u8(v: int) -> str:
    return f"{v} 0b{v:08b}"


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    port = sys.argv[2] if len(sys.argv) > 2 else "COM6"

    from pyocd.core.helpers import ConnectHelper

    # ⚠ connect_mode 必须是 attach！
    # pyocd 默认是 halt —— 一连上就把内核停住，固件立刻停止执行，
    # 330 那边随即失联、整机卡死。2026-09-17 就这么把台面上的 316 冻住过一次。
    # attach = 只挂到总线上读写内存，不碰内核状态，目标继续正常跑。
    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        line("!! 没找到 ST-Link")
        (ROOT / "tools" / "read_316_fan_state.txt").write_text("\n".join(LINES), encoding="utf-8")
        return 1
    session.open()
    tgt = session.target
    # 保险：万一进来时内核就是停的（上一次没恢复/别处停的），把它放开。
    if tgt.get_state() == tgt.State.HALTED:
        line("!! 进入时内核处于 HALTED —— 已 resume 放开")
        tgt.resume()
    line(f"已连接 ST-Link -> {tgt.part_number}  state={tgt.get_state().name}")

    def r8(a: int) -> int:
        return tgt.read_memory_block8(a, 1)[0]

    def r16s(a: int) -> int:
        v = tgt.read_memory_block8(a, 2)
        x = v[0] | (v[1] << 8)
        return x - 0x10000 if x & 0x8000 else x

    def r32(a: int) -> int:
        v = tgt.read_memory_block8(a, 4)
        return v[0] | (v[1] << 8) | (v[2] << 16) | (v[3] << 24)

    # 316 内部量（绝对地址）
    INTERNAL = [
        ("OutdoorFanStage", 0x20000D00, 8),
        ("OutdoorVfdOn", 0x20000D01, 8),
        ("OutdoorFixedOn", 0x20000D02, 8),
        ("OutdoorHeatTwoFan", 0x20000D04, 8),
        ("OutdoorTypeIIFan2High", 0x20000D06, 8),
        ("OutdoorTypeIIFan2SwapDead", 0x20000D07, 8),
        ("OutdoorTypeIIStage", 0x20000D08, 8),
        ("OutdoorTypeIIPendingStage", 0x20000D09, 8),
        ("OutdoorFaultHoldFanMask", 0x20000D13, 8),
        ("AmbientLockout", 0x20000D17, 8),
        ("OutdoorFanChangeSeconds", 0x20000D28, 32),
        ("OutdoorFanNoCompSeconds", 0x20000D2C, 32),
        ("OutdoorVfdSpeed", 0x20000D30, 32),
        ("OutdoorHeatFanHighCount", 0x20000D34, 32),
        ("OutdoorHeatFanLowCount", 0x20000D38, 32),
        ("OutdoorTypeIIPendingCount", 0x20000D54, 32),
        ("InDefrost", 0x20000DB0, 8),
    ]

    def snapshot() -> dict[str, object]:
        s: dict[str, object] = {}
        for name, a, size in INTERNAL:
            s[name] = r8(a) if size == 8 else r32(a)
        for name, idx in IDX.items():
            s[f"P.{name}"] = r16s(p_addr(idx))
        s["AI[6]"] = tgt.read_memory_block8(ABS["AI"] + 12, 2)[0] | (
            tgt.read_memory_block8(ABS["AI"] + 13, 1)[0] << 8
        )
        s["SensorStatus[0..6]"] = tuple(r8(ABS["SensorStatus"] + i) for i in range(7))
        s["FanRunSec"] = (r32(0x20000DA0), r32(0x20000DA4))
        s["FanStopSec"] = (r32(0x20000DA8), r32(0x20000DAC))
        s["FanCmdRunSec"] = (r32(0x2000005C), r32(0x20000060))
        s["Comp[0..1]"] = (r8(0x20000DD4), r8(0x20000DD5))
        s["output[0..7]"] = tuple(r8(0x200000D4 + i) for i in range(8))
        return s

    line()
    line("=== 316（外机1）内部量 初值 ===")
    first = snapshot()
    for k, v in first.items():
        line(f"  {k:26s} = {v}")

    # 单调递增的计时器每秒都在变，逐次记录会把日志刷满。只在时间线里体现。
    NOISY = {
        "OutdoorFanChangeSeconds", "OutdoorFanNoCompSeconds",
        "OutdoorHeatFanHighCount", "OutdoorHeatFanLowCount",
        "OutdoorTypeIIPendingCount", "FanRunSec", "FanStopSec", "FanCmdRunSec",
        "AI[6]", "SensorStatus[0..6]", "output[0..7]",
    }
    # 时间线里最关心的几个
    TL = ["Comp[0..1]", "P.FanOpenSet", "P.FanOpenSet2", "OutdoorFanStage",
          "OutdoorHeatTwoFan", "OutdoorTypeIIStage", "OutdoorTypeIIFan2High",
          "P.EnviTempAI0Disp", "OutdoorFanNoCompSeconds", "OutdoorHeatFanLowCount",
          "OutdoorHeatFanHighCount", "OutdoorFanChangeSeconds"]

    line()
    line(f"=== 采样 {seconds:.0f} 秒：关键量一变化就记；每 30s 打一行时间线 ===")
    prev = first
    t0 = time.time()
    next_tl = 0.0
    next_wd = 0.0
    while time.time() - t0 < seconds:
        time.sleep(0.5)
        el = time.time() - t0
        # 看门狗：每 10s 查一次内核有没有被停住（调试口出错时会），停了立刻放开。
        if el >= next_wd:
            next_wd = el + 10.0
            if tgt.get_state() == tgt.State.HALTED:
                line(f"  [{el:6.1f}s] !! 检测到 HALTED —— 立即 resume 放开")
                tgt.resume()
        cur = snapshot()
        diff = {k: (prev[k], cur[k]) for k in cur
                if cur[k] != prev[k] and k not in NOISY}
        for k, (a, b) in diff.items():
            line(f"  [{el:6.1f}s] {k:26s} {a}  ->  {b}")
        prev = cur
        if el >= next_tl:
            next_tl = el + 30.0
            line("  T+%4.0fs | %s" % (el, "  ".join(f"{k.split('.')[-1]}={cur[k]}" for k in TL)))

    line()
    line("=== 316 内部量 终值 ===")
    for k, v in prev.items():
        line(f"  {k:26s} = {v}")

    # 收尾再确认一次没把内核留在停机态 —— 留下就是"板子卡死"。
    if tgt.get_state() == tgt.State.HALTED:
        line("!! 采样结束时内核 HALTED —— 已 resume 放开")
        tgt.resume()
    line(f"结束 state={tgt.get_state().name}")
    session.close()

    # ---- COM6：330 侧寄存器 ----
    line()
    line("=== 330 侧（COM6）寄存器 ===")
    try:
        import app as m

        c = m.ModbusRtuClient()
        c.open(port, m.DEFAULT_BAUD)

        def rd(a: int, n: int = 1):
            for _ in range(3):
                try:
                    return c.read_holding_registers(1, a, n)
                except Exception:  # noqa: BLE001
                    time.sleep(0.2)
            return [-1] * n

        try:
            for u in (1, 2):
                b = 1550 + (u - 1) * 70
                g = m.OUTDOOR_GATEWAY_BASE + (u - 1) * m.OUTDOOR_GATEWAY_STEP
                st = rd(b, 7)
                fan = rd(b + 43, 7)
                io_ = rd(b + 50)[0]
                y = (io_ >> 8) & 0xFF
                line(f"--- {u}#外机 ---")
                line(f"  环温镜像 330[{b+2}] = {st[2] / 10.0} C")
                line(f"  压机1/2 状态 = {st[5]}/{st[6]}")
                line(f"  风机目标={fan[0]} 反馈1={fan[1]} 反馈2={fan[2]} DA0={fan[3+2] / 100.0:.2f}V")
                line(f"  Y位 = {y:08b}  Y02单速={y & 1 << 2 and 1 or 0} Y03双速低={y & 1 << 3 and 1 or 0} "
                     f"Y07双速高={y & 1 << 7 and 1 or 0} Y06曲轴={y & 1 << 6 and 1 or 0}")
                cfg = rd(g, 17)
                line(f"  机型={cfg[0]} 风机类型={cfg[1]}  Z={cfg[9] / 10.0}C ZD={cfg[10] / 10.0}C "
                     f"(Z+ZD={cfg[9] / 10.0 + cfg[10] / 10.0:.1f}C)")
            line()
            line(f"  330[700] SysStatus={rd(700)[0]}  330[709] SysStep={rd(709)[0]}  "
                 f"330[723] OilHeatingFlag={rd(723)[0]}  330[236] 模式={rd(236)[0]}")
        finally:
            c.close()
    except Exception as exc:  # noqa: BLE001
        line(f"  !! 串口读取失败: {exc}")

    (ROOT / "tools" / "read_316_fan_state.txt").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
