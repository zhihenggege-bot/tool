"""类型4（变频+定速）阶梯实测 —— 验 V12.13「变频风机关」。

外机2：机型=2 风机类型=4。按规格书流程图《双风机室外机时（一定一变）》：

    升档: 变频低->高   --(变频到最高频)--> 定频开 + 变频回最低
          变频低->高   --(变频到最高频)--> 顶
    降档: 变频高->低   --(定频已开, 变频到最低)--> 定频关 + 变频回最高
          变频高->低   --(定频已关, 变频到最低)--> 【变频风机关】

判据来自 OutdoorFanTypeIII()（UserAction.c:1433）—— 三个阈值在代码里是**写死的**，
不随 TL/TLD 走（已核对 UserAction.c:1459/1464/1482）：
    NeedLoad   = 冷凝 > 36.0        (1459)
    NeedUnload = 冷凝 < 34.0        (1464)
    34.0~36.0 保持                  <-- 这就是规格书给的那条迟滞带
    冷凝 > 45.0 -> 风机没开时满频启动 / 预启动满频   (1482/1495)

改 V12.13 的那一支是「定频已关」的 else：
    else if(VfdOn && RunSeconds[0] >= FanMinRunTimeSet && ChgSec >= 15)
        VfdOn = 0; VfdSpeed = 0;     <-- 此时定频也是关的 => 两台全关

⚠ 压缩机必须运行，否则本函数根本不被调用（UserAction.c:1652 提前返回）。
  用 --ambient 把环温推高，让内机产生制冷需求把压机拉起来。

跑法：
    python.exe tools/test_316_type4_ladder.py --setup      # 台面参数（快扫）+ 起压机
    python.exe tools/test_316_type4_ladder.py --run        # 走完整条阶梯，10Hz 采样
    python.exe tools/test_316_type4_ladder.py --restore    # 参数/偏移还原
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

import pt_tables as pt  # noqa: E402

PORT = "COM6"
SLAVE = 1
GW_BASE = 1830
GW_DIAG = 42
GW_STEP = 48
AI_HMI_BASE = 2680
AI_UNIT_WORDS = 49
AI_CH_WORDS = 12
AI_OFFSET_IN_CH = 8
AI_P316_BASE = 302
STATUS_BASE = 1550
OFF_HP1 = 23
OFF_HP2 = 25
COMPACT_BASE = 2534          # OUTDOOR_COMPACT_BASE
COMPACT_STEP = 16
MAX_TARGET_KPA = 3400
REF = 3                      # R410A

# ---- 316 RAM（V12.13 map 复核过，与 V12.12 一致：新代码只落 .text）----
PARAM_BASE = 0x2000164A
A_STAGE = 0x20000D00
A_VFD_ON = 0x20000D01
A_FIXED_ON = 0x20000D02
A_CHGSEC = 0x20000D28
A_VFD_SPEED = 0x20000D30
A_VFD_LOAD = 0x20000D48
A_VFD_UNLOAD = 0x20000D4C
A_OUTPUT = 0x200000D4
A_RUNSEC = 0x20000DA0        # unsigned int[2]
A_STOPSEC = 0x20000DA8       # unsigned int[2]

# ---- Parameter 下标 ----
IDX_UNITTYPE = 165
IDX_FANTYPE = 166
IDX_TL = 172
IDX_TLD = 173
IDX_STEP = 178               # ×10 = 0.1Hz/s
IDX_MINRUN = 179
IDX_MINSTOP = 180
IDX_ENVI = 1420 + 2
IDX_COMP = 872 - 872 + 0     # 占位，实际用下面的 COMP 地址

BENCH_STEP = 100             # 10.0 Hz/s（原 10 = 1.0Hz/s）—— 让整条阶梯能在几十秒内走完
BENCH_MINRUN = 2
BENCH_MINSTOP = 2

LOG: list[str] = []


def say(s: str = "") -> None:
    LOG.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "test_316_type4_ladder.txt").write_text(
        "\n".join(LOG) + "\n", encoding="utf-8")


def kpa_for(tc: float, ref: int = REF) -> int:
    lo, hi = 0, pt.pressure_max_kpa(ref)
    while lo < hi:
        mid = (lo + hi) // 2
        if pt.pt_temp(ref, mid) < tc:
            lo = mid + 1
        else:
            hi = mid
    return lo


def main() -> int:
    import app as m
    from pyocd.core.helpers import ConnectHelper

    def opt(name, default=None):
        if name not in sys.argv:
            return default
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default

    unit = int(opt("--unit", 2))
    case = "run"
    for c in ("--setup", "--run", "--ascent", "--restore", "--status"):
        if c in sys.argv:
            case = c[2:]

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

    gw = GW_BASE + (unit - 1) * GW_STEP
    win = AI_HMI_BASE + (unit - 1) * AI_UNIT_WORDS
    st = STATUS_BASE + (unit - 1) * 70
    compact = COMPACT_BASE + (unit - 1) * COMPACT_STEP
    hmi = [win + i * AI_CH_WORDS + AI_OFFSET_IN_CH for i in range(2)]

    def gw_write(addr, target, tag):
        deadline = time.time() + 30
        while time.time() < deadline:
            if s16(rd(gw + GW_DIAG + 1)[0]) != 1:
                break
            time.sleep(0.35)
        t0 = time.time()
        try:
            client.write_single_register(SLAVE, addr, target & 0xFFFF)
        except Exception as exc:  # noqa: BLE001
            say(f"  !! [{tag}] 写 330[{addr}] 异常: {exc}")
            return False
        time.sleep(0.08)
        while time.time() - t0 < 45:
            time.sleep(0.5)
            if s16(rd(addr)[0]) == target:
                say(f"  [{tag}] OK {time.time() - t0:.1f}s  330[{addr}]={target}")
                return True
        say(f"  !! [{tag}] 超时 330[{addr}] 回读={s16(rd(addr)[0])} 期望={target}")
        return False

    def set_cond(tc, tag):
        """把两路高压都推到 tc 对应的 kPa（CondTempMax == CondTempMin，段判据干净）。"""
        hp = [s16(rd(st + OFF_HP1)[0]), s16(rd(st + OFF_HP2)[0])]
        off = [s16(rd(hmi[0])[0]), s16(rd(hmi[1])[0])]
        base = [hp[i] - off[i] for i in range(2)]
        want = kpa_for(tc)
        tgt = [want - base[i] for i in range(2)]
        say(f"  冷凝 {tc:.1f}C = {want} kPa -> 偏移 AI0={tgt[0]} AI1={tgt[1]}")
        for i in range(2):
            if not gw_write(hmi[i], tgt[i], f"AI{i}"):
                return False
        hp = [s16(rd(st + OFF_HP1)[0]), s16(rd(st + OFF_HP2)[0])]
        say(f"  现在 高压1={hp[0]}({pt.pt_temp(REF, hp[0]):.1f}C) "
            f"高压2={hp[1]}({pt.pt_temp(REF, hp[1]):.1f}C)")
        return True

    # ---------- 读配置 ----------
    def r16s(i):
        v = rd(IDX_ENVI)[0]
        return s16(v)

    # 参数走 ST-Link 直读更准（330 网关只开放 21 个）
    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
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

    def prm(i):
        b = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        v = b[0] | (b[1] << 8)
        return v - 0x10000 if v & 0x8000 else v

    def r8(a):
        return tgt.read_memory_block8(a, 1)[0]

    def r32(a):
        b = tgt.read_memory_block8(a, 4)
        return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)

    ver = [prm(1000 + i) for i in range(6)]
    say(f"槽位={unit}  版本={ver}")
    if ver[2] != 13:
        say(f"!! 预期 minor=13（V12.13），实际 {ver[2]} —— 请先烧录新固件，测试才有意义")
    say(f"机型={prm(IDX_UNITTYPE)} 风机类型={prm(IDX_FANTYPE)}")
    say(f"TL={prm(IDX_TL) / 10.0:.1f} TLD={prm(IDX_TLD) / 10.0:.1f}"
        f"  （阈值写死在代码里：加载>36.0 减载<34.0 满频>45.0）")
    say(f"加减载={prm(IDX_STEP) / 10.0:.1f}Hz/s  最短运行={prm(IDX_MINRUN)}s  最短停止={prm(IDX_MINSTOP)}s")
    say(f"环温={prm(IDX_ENVI) / 10.0:.1f}C")
    say()

    if case == "status":
        session.close()
        client.close()
        write()
        return 0

    # ---------- 台面参数 ----------
    PARAM_HMI_BASE = 2680 + 190   # 台面参数不在网关 21 个里，走 330 的 HMI 参数区
    # ⚠ 这几个参数通过 330 网关不可写；用 ST-Link 直接改 RAM 会被每扫描的
    #   "参数从 EEPROM 同步" 覆盖。所以台面快扫只能靠 HMI 面板手工设。
    if case in ("setup", "restore"):
        say("台面参数（加减载速度 / 最短运行 / 最短停机）请在上位机 HMI 面板里改：")
        say("  setup    : 变频轴流风机加减载速度=10.0 Hz/s, 最短运行=2s, 最短停止=2s")
        say("  restore  : 加减载速度=1.0 Hz/s, 最短运行=30s, 最短停止=30s")
        say("（网关只开放 21 个参数，这三项不在其中；写不进就别改，用原值跑，只是慢些）")

    # ---------- 主测试：走阶梯 ----------
    if case in ("run", "ascent"):
        if case == "ascent":
            # 补测升档方向。--run 那一轮进 C1~C4 时风机已经在 S2 顶上了
            # （上一支探针把速度留在 31Hz，等脚本写完 AI 偏移它已经爬完），
            # 所以「段1 变频低->高 -> 到最高频 -> 定频开 + 变频回最低」这一段
            # 没有被逐帧记录到。这里先降到 S0，再从 40C 走一遍升档。
            plan = [
                (30.0, 150, "降到 S0（变频风机关、两台全关）"),
                (40.0, 170, "升档：变频低->高 -> 最高频 -> 定频开+变频回最低 -> 再升到最高"),
            ]
        else:
            plan = [
                (47.0, 90, "冷凝47 -> 若压机刚起，变频应满频启动（规格书：风机没开且冷凝>45 满频）"),
                (40.0, 120, "冷凝40 -> 加载：变频低->高（定频不开）"),
                (40.0, 90, "定频开 + 变频回最低 -> 双风机"),
                (40.0, 120, "定频保持开，变频再升到最高"),
                (30.0, 120, "冷凝30 -> 减载：变频降到底 -> 定频关 + 变频回最高"),
                (30.0, 150, "继续减载：变频降到底 -> 【V12.13 变频风机关】两台全关"),
                (47.0, 150, "冷凝47 -> 停机满 30s 后重启，且 >45 应直接满频"),
                (35.0, 60, "冷凝35 在保持带 34~36 -> 加减载都不动"),
            ]
        say("=== 类型4 阶梯实测 ===")
        # ⚠ 第 9/10 列是 RunSeconds[0]/RunSeconds[1]（变频/定速风机的**运行**秒数），
        #   不是 Run/Stop。原来表头写成 "Run0 Stop0" 是错的，会让读数看着自相矛盾
        #   （两只风机不可能同时既在运行又刚停机）。
        say(" t(s) | 环温 | 冷凝1 冷凝2 | VfdOn FixOn VfdHz | Stage | RunVFD RunFIX | ChgSec | Load Unld | Y02 Y03 Y07")
        t00 = time.time()
        for tc, hold, desc in plan:
            say("")
            say(f"--- {desc} ---")
            if not set_cond(tc, f"{tc:.0f}C"):
                break
            t_start = time.time()
            nxt = 0.0
            nxt_rd = 0.0
            prev = None
            cond1 = cond2 = 0
            while time.time() - t_start < hold:
                el = time.time() - t_start
                if el >= nxt:
                    nxt = el + 10
                    if tgt.get_state() == tgt.State.HALTED:
                        say(f"  [{el:5.1f}] !! HALTED —— resume")
                        tgt.resume()
                if el >= nxt_rd:
                    # 机型2 的冷凝温度来自高压传感器 —— 每秒从 330 状态块读一次，
                    # 不塞进 10Hz 内层循环（Modbus 往返会把采样拖慢）。
                    nxt_rd = el + 1.0
                    cond1 = s16(rd(st + OFF_HP1)[0])
                    cond2 = s16(rd(st + OFF_HP2)[0])
                out = [r8(A_OUTPUT + i) for i in range(8)]
                cur = (r8(A_VFD_ON), r8(A_FIXED_ON), r32(A_VFD_SPEED), r8(A_STAGE),
                       r32(A_RUNSEC), r32(A_RUNSEC + 4), r32(A_STOPSEC), r32(A_STOPSEC + 4),
                       r32(A_CHGSEC), r32(A_VFD_LOAD), r32(A_VFD_UNLOAD),
                       out[2], out[3], out[7])
                if cur != prev:
                    say("  ".join((
                        "%5.0f" % (time.time() - t00),
                        "%5.1f" % (s16(rd(st + 2)[0]) / 10.0),
                        "%5.1f" % pt.pt_temp(REF, cond1), "%5.1f" % pt.pt_temp(REF, cond2),
                        "%5d" % cur[0], "%5d" % cur[1], "%6.1f" % (cur[2] / 10.0),
                        "%5d" % cur[3],
                        "%5d" % cur[4], "%5d" % cur[5],
                        "%6d" % cur[8],
                        "%4d" % cur[9], "%4d" % cur[10],
                        "%3d" % cur[11], "%3d" % cur[12], "%3d" % cur[13],
                    )))
                    prev = cur
                time.sleep(0.1)
            say(f"  （保持 {hold}s 结束）")

        say("")
        say("=== 结束，还原高压偏移到 0（回自然读数）===")
        for i in range(2):
            gw_write(hmi[i], 0, f"还原AI{i}")
        hp = [s16(rd(st + OFF_HP1)[0]), s16(rd(st + OFF_HP2)[0])]
        say(f"  还原后 高压1={hp[0]}({pt.pt_temp(REF, hp[0]):.1f}C) "
            f"高压2={hp[1]}({pt.pt_temp(REF, hp[1]):.1f}C)")

    if tgt.get_state() == tgt.State.HALTED:
        say("!! 结束 HALTED —— resume")
        tgt.resume()
    session.close()
    client.close()
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
