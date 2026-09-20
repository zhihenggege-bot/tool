"""把某台外机的某一路 NTC 读数推到指定值（台面造工况用）。

链路（2026-09-17 逐环核对）：
    NTC[i] = round(Tempbuf*10) + Parameter[493-i]        （NTC16bit.c:171）
    镜像对  Parameter[1580+i] <-> Parameter[499-i]        （UserAction.c:254/268）
    两者错开 6  ->  NTC[i] 读的 Parameter[493-i] == Parameter[1586+i]
    -> 330[2534 + (u-1)*16 + i] 就是 NTC[i] 的偏移（台面块 +0~7 = 8 路 NTC 校准）

    i=0  环温   (EnviTempAI0Disp = Parameter[1420+2]，= AI[6])
    i=1  翅片1  (FinTemp1        = Parameter[1420+11]，= AI[7])
    i=2  翅片2  (FinTemp2        = Parameter[1420+12]，= AI[8])

⚠ 偏移是**加法**：显示值 = 真实值 + 偏移。
   本脚本用 ST-Link 读 316 侧的**显示值**、用 Modbus 读偏移，反推真实值再算新偏移。
   写 0 = 还原。

⚠ 330 状态块（1550+(u-1)*70）里**只有环温**（+2），没有翅片 —— 所以显示值必须从
   316 侧读，不能只靠 Modbus。

跑法：
    python.exe tools/inject_316_ntc.py --unit 2 --show
    python.exe tools/inject_316_ntc.py --unit 2 --set 1=-8.0 2=-8.0
    python.exe tools/inject_316_ntc.py --unit 2 --restore
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT = "COM6"
SLAVE = 1
GW_BASE = 1830
GW_DIAG = 42
COMPACT_BASE = 2534
COMPACT_NUM = 16
PARAM_BASE = 0x2000164A
PLCREAD = 1420

# 显示值统一从 316 的 AI[6+i] 读（NTC16bit.c:182-189 就是 AI[6..13]=NTC[0..7]），
# 比原先只认 3 路的 Parameter[PLCREAD+..] 通用。
A_AI = 0x20001172          # int16 AI[14]，NTC[i] == AI[6+i]

# NTC 下标 -> 名字（User.h:223-229）
NTC_NAME = {
    0: "环温   NTC1",
    1: "翅片1  NTC2",
    2: "翅片2  NTC3",
    3: "排气   NTC4",
    4: "排气   NTC5",
    5: "吸气1  NTC6",   # SuctionTempAI16 = AI[11]  <- 3.9 过热度用这个
    6: "吸气2  NTC7",   # SuctionTempAI17 = AI[12]
    7: "(未用)",
}
SHOW = {i: (None, NTC_NAME[i]) for i in NTC_NAME}

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write_out() -> None:
    (pathlib.Path(__file__).resolve().parent / "inject_316_ntc.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


def main() -> int:
    import app as m  # noqa: E402
    from pyocd.core.helpers import ConnectHelper

    def opt(name, default=None):
        if name not in sys.argv:
            return default
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default

    unit = int(opt("--unit", 2))
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

    gw = GW_BASE + (unit - 1) * m.OUTDOOR_GATEWAY_STEP
    comp = COMPACT_BASE + (unit - 1) * COMPACT_NUM

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        say("!! 没找到 ST-Link（显示值必须从 316 侧读）")
        client.close()
        write_out()
        return 1
    session.open()
    tgt = session.target
    if tgt.get_state() == tgt.State.HALTED:
        say("!! 进入时 HALTED —— 已 resume")
        tgt.resume()

    def p16(i):
        b = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        v = b[0] | (b[1] << 8)
        return v - 0x10000 if v & 0x8000 else v

    def ai(i):
        """NTC[i] 的当前显示值（0.1C），来自 AI[6+i]。"""
        b = tgt.read_memory_block8(A_AI + (6 + i) * 2, 2)
        v = b[0] | (b[1] << 8)
        return v - 0x10000 if v & 0x8000 else v

    def snapshot():
        out = {}
        for i in SHOW:
            out[i] = (ai(i), s16(rd(comp + i)[0]))
        return out

    def show(snap):
        say(f"--- 外机{unit} NTC（偏移在 330[{comp}..{comp + 7}]）---")
        for i, (pst, nm) in SHOW.items():
            disp, off = snap[i]
            say("  NTC[%d] %-6s 显示 %6.1fC  偏移 %5d (%+.1fC)   -> 真实 %.1fC"
                % (i, nm, disp / 10.0, off, off / 10.0, (disp - off) / 10.0))

    snap = snapshot()
    show(snap)

    # ⚠ 不能用 opt("--set")：它只取紧跟其后的一个 argv，`--set 1=.. 2=..` 会丢掉第二个。
    #   这里扫全部非选项参数，凡含 "=" 的都收。
    targets: dict[int, float] = {}
    for a in sys.argv[1:]:
        if "=" in a and not a.startswith("--"):
            k, v = a.split("=", 1)
            try:
                targets[int(k)] = float(v)
            except ValueError:
                say(f"  !! 参数格式不对: {a}")
    if "--restore" in sys.argv:
        targets = {i: 0.0 for i in SHOW}
    if not targets:
        session.close()
        client.close()
        write_out()
        return 0

    for i in sorted(targets):
        if i not in SHOW:
            say(f"  !! NTC[{i}] 不在已知通道表里，跳过")
            continue
        disp, cur_off = snap[i]
        real = disp - cur_off
        new_off = int(round(targets[i] * 10)) - real
        say(f"  NTC[{i}] {SHOW[i][1]}: 显示 {disp / 10.0:.1f}C 偏移 {cur_off}"
            f" -> 目标 {targets[i]:.1f}C  新偏移 {new_off}")
        deadline = time.time() + 30
        while time.time() < deadline:
            if s16(rd(gw + GW_DIAG + 1)[0]) != 1:
                break
            time.sleep(0.35)
        t0 = time.time()
        try:
            client.write_single_register(SLAVE, comp + i, new_off & 0xFFFF)
        except Exception as exc:  # noqa: BLE001
            say(f"    !! 写异常: {exc}")
            continue
        time.sleep(0.08)
        ok = False
        while time.time() - t0 < 45:
            time.sleep(0.5)
            if s16(rd(comp + i)[0]) == new_off:
                ok = True
                break
        say(f"    {'OK' if ok else '!! 超时'}  {time.time() - t0:.1f}s")

    say()
    show(snapshot())
    if tgt.get_state() == tgt.State.HALTED:
        say("!! 结束 HALTED —— resume")
        tgt.resume()
    session.close()
    client.close()
    write_out()
    return 0


if __name__ == "__main__":
    sys.exit(main())
