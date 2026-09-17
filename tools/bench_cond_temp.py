"""台面工具：把某台外机的「冷凝温度」推到指定值，然后盯变频风机状态。

冷凝温度 = 高压传感器换算。316 每扫描从 HighPressDisp 现算，往 RAM 写没用，
所以从**输入端**偏 —— 改 316 的 AiCfgOffset（AI0 = 1#高压、AI1 = 2#高压）：

    330[2680 + (u-1)*49 + 8]        -> 316[310]   AI0 校准偏移 (kPa)
    330[2680 + (u-1)*49 + 12 + 8]   -> 316[322]   AI1 校准偏移 (kPa)

走 330 网关转发。写协议照抄工具 app.py 的 write_outdoor_gateway_register()：
  1. 等网关写槽空闲（330[base+43] != 1）
  2. FC06 单寄存器写（多寄存器会被 330 的 modbus.c 丢帧）
  3. **判据只看镜像回读 == 目标值**（状态位比镜像早约 5.5 秒，且会读到上一轮遗留值）
  → 一次写约 15 秒

两路都设成同一个值，让 CondTempMax == CondTempMin，段判据干净。

环温同理：`EnviTempAI0Disp = AI[6] = NTC[0]`，而
`NTC[0] = round(Tempbuf*10) + Parameter[493]`；`Parameter[493]` 由 316 从镜像块
`Parameter[1586]` 自动同步（UserAction.c: 1580+i <-> 499-i）。所以

    330[2534 + (u-1)*16 + 0]   -> 316[1586]   环境温度校准偏移 (0.1C)

⚠ 台面 2#外机的环温偏移现在是 127（+12.7C），真实室温 7.3C 被报成 20.0C。
   改之前记下原值，测完要用 `--ambient-offset` 放回去，**不要清 0**。

跑法：
    python tools/bench_cond_temp.py 35.0                     # 1#外机 -> 35.0C，盯 60 秒
    python tools/bench_cond_temp.py 47.0 --unit 2 --watch 120
    python tools/bench_cond_temp.py --restore                # 两路高压偏移清零
    python tools/bench_cond_temp.py --unit 2 --ambient 7.0   # 把 2# 环温推到 7.0C
    python tools/bench_cond_temp.py --unit 2 --ambient-offset 127   # 放回原偏移
    python tools/bench_cond_temp.py 35.0 --dry-run           # 只算不写
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
GW_BASE = 1830              # OUTDOOR_GATEWAY_BASE
GW_DIAG = 42                # OUTDOOR_GATEWAY_DIAG_OFFSET
AI_HMI_BASE = 2680          # OUTDOOR_AI_CFG_HMI_BASE
AI_UNIT_WORDS = 49
AI_CH_WORDS = 12
AI_OFFSET_IN_CH = 8         # 通道内偏移字段
AI_P316_BASE = 302
STATUS_BASE = 1550
OFF_HP1_IN_STATUS = 23      # 1#高压 kPa
OFF_HP2_IN_STATUS = 25      # 2#高压 kPa
MAX_TARGET_KPA = 3400       # 高压保护在 3800 动作，留足余量

REF = 3                     # R410A（读 330[39] 可覆盖）

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def kpa_for(temp_c: float, ref: int = REF) -> int:
    """冷凝温度 -> 需要的高压 kPa（查 316 的 R410A 表反解）。"""
    lo, hi = 0, pt.pressure_max_kpa(ref)
    while lo < hi:
        mid = (lo + hi) // 2
        if pt.pt_temp(ref, mid) < temp_c:
            lo = mid + 1
        else:
            hi = mid
    return lo


def main() -> int:
    import app as m

    def opt(name: str, default=None):
        if name not in sys.argv:
            return default
        idx = sys.argv.index(name)
        if idx + 1 >= len(sys.argv):
            return default
        return sys.argv[idx + 1]

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # 去掉紧跟选项后面的值，免得被当成目标温度
    for name in ("--unit", "--watch", "--ambient", "--ambient-offset", "--hp1", "--hp2"):
        v = opt(name)
        if v is not None and v in args:
            args.remove(v)
    watch = float(opt("--watch", 60.0))
    dry = "--dry-run" in sys.argv
    restore = "--restore" in sys.argv
    unit = int(opt("--unit", 1))
    ambient = opt("--ambient")
    ambient_offset = opt("--ambient-offset")
    # 分别设两路高压（验「强制段4」必需：强制判据用 CondTempMax，段界用 CondTempMin，
    # 两路设成同一个值就分不出是常规段4 还是强制段4）
    hp1 = opt("--hp1")
    hp2 = opt("--hp2")

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    def rd(addr: int, n: int = 1) -> list[int]:
        for _ in range(4):
            try:
                return client.read_holding_registers(SLAVE, addr, n)
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        return [-1] * n

    def s16(v: int) -> int:
        v &= 0xFFFF
        return v - 0x10000 if v & 0x8000 else v

    gw = GW_BASE + (unit - 1) * m.OUTDOOR_GATEWAY_STEP
    win = AI_HMI_BASE + (unit - 1) * AI_UNIT_WORDS
    st = STATUS_BASE + (unit - 1) * 70
    hmi = [win + 0 * AI_CH_WORDS + AI_OFFSET_IN_CH, win + 1 * AI_CH_WORDS + AI_OFFSET_IN_CH]
    p316 = [AI_P316_BASE + 0 * AI_CH_WORDS + AI_OFFSET_IN_CH,
            AI_P316_BASE + 1 * AI_CH_WORDS + AI_OFFSET_IN_CH]

    compact = m.OUTDOOR_COMPACT_BASE + (unit - 1) * m.OUTDOOR_COMPACT_COUNT

    ref = s16(rd(39)[0])
    if ref not in (0, 1, 2, 3):
        ref = REF
    say(f"外机{unit}#  制冷剂={pt.REFRIGERANT_NAMES.get(ref, ref)}  网关基址={gw}  AI窗口={win}")
    say(f"  高压偏移: 330[{hmi[0]}]->316[{p316[0]}] (AI0)   330[{hmi[1]}]->316[{p316[1]}] (AI1)")
    say(f"  环温偏移: 330[{compact}]->316[1586] (环境温度)")

    # ---- 环温 ----
    amb_now = s16(rd(st + 2)[0])
    amb_off = s16(rd(compact)[0])
    amb_base = amb_now - amb_off
    say(f"  当前环温={amb_now / 10.0:.1f}C（偏移={amb_off}，无偏移读数={amb_base / 10.0:.1f}C）")

    def write_gw(addr: int, target: int, tag: str) -> None:
        deadline = time.time() + 30
        state = -1
        while time.time() < deadline:
            state = s16(rd(gw + GW_DIAG + 1)[0])
            if state != 1:
                break
            time.sleep(0.35)
        say(f"  [{tag}] 网关空闲(状态={state})，写 330[{addr}] = {target} ...")
        t0 = time.time()
        try:
            client.write_single_register(SLAVE, addr, target & 0xFFFF)
        except Exception as exc:  # noqa: BLE001
            say(f"  !! 写 330[{addr}] 异常: {exc}")
            return
        time.sleep(0.08)
        ok = False
        while time.time() - t0 < 45:
            time.sleep(0.5)
            if s16(rd(addr)[0]) == target:
                ok = True
                break
        say(f"  [{tag}] {'OK' if ok else '!! 超时'}  用时 {time.time() - t0:.1f}s  "
            f"回读 330[{addr}]={s16(rd(addr)[0])}")

    if ambient is not None or ambient_offset is not None:
        want = int(round(float(ambient_offset))) if ambient_offset is not None \
            else int(round(float(ambient) * 10)) - amb_base
        say(f"  >>> 环温偏移 -> {want}（目标环温 "
            f"{(amb_base + want) / 10.0:.1f}C）")
        if dry:
            say("  (--dry-run，不写)")
        else:
            write_gw(compact, want, "环温")
        say(f"  现在环温={s16(rd(st + 2)[0]) / 10.0:.1f}C（偏移={s16(rd(compact)[0])}）")
        client.close()
        _write()
        return 0

    hp = [s16(rd(st + OFF_HP1_IN_STATUS)[0]), s16(rd(st + OFF_HP2_IN_STATUS)[0])]
    off = [s16(rd(hmi[0])[0]), s16(rd(hmi[1])[0])]
    say(f"  当前: 高压1={hp[0]} kPa ({pt.pt_temp(ref, hp[0]):.1f}C, 偏移={off[0]})"
        f"   高压2={hp[1]} kPa ({pt.pt_temp(ref, hp[1]):.1f}C, 偏移={off[1]})")

    if restore:
        targets = [0, 0]
        say("  >>> 恢复：两路偏移清零")
    else:
        if not args and hp1 is None and hp2 is None:
            say("用法: bench_cond_temp.py <目标温度C> [--watch 秒] [--dry-run] [--restore]")
            say("      bench_cond_temp.py --unit N --ambient T | --ambient-offset V")
            say("      bench_cond_temp.py --unit N --hp1 T1 --hp2 T2   （两路分别设）")
            return 2
        base_kpa = [hp[i] - off[i] for i in range(2)]
        if args:
            want_c = float(args[0])
            want_kpa = kpa_for(want_c, ref)
            want_cs = [want_c, want_c]
        else:
            want_cs = [float(hp1 if hp1 is not None else hp2),
                       float(hp2 if hp2 is not None else hp1)]
            want_kpa = None
        kpas = [kpa_for(c, ref) for c in want_cs]
        for k in kpas:
            if k > MAX_TARGET_KPA:
                say(f"!! 目标 {k} kPa 超过安全上限 {MAX_TARGET_KPA}（高压保护 3800），拒绝")
                return 2
        targets = [kpas[i] - base_kpa[i] for i in range(2)]
        say(f"  无偏移读数 {base_kpa[0]}/{base_kpa[1]} kPa")
        say(f"  目标: 高压1 {want_cs[0]:.1f}C = {kpas[0]} kPa   高压2 {want_cs[1]:.1f}C = {kpas[1]} kPa")
        say(f"  >>> 新偏移: AI0={targets[0]}  AI1={targets[1]}")
        for t in targets:
            if not -5000 <= t <= 5000:
                say(f"!! 偏移 {t} 超范围，拒绝")
                return 2

    if dry:
        say("  (--dry-run，不写)")
    else:
        for i in range(2):
            addr, target = hmi[i], targets[i]
            # 1) 等网关空闲
            deadline = time.time() + 30
            while time.time() < deadline:
                state = s16(rd(gw + GW_DIAG + 1)[0])
                if state != 1:
                    break
                time.sleep(0.35)
            say(f"  [AI{i}] 网关空闲(状态={state})，写 330[{addr}] = {target} ...")
            t0 = time.time()
            try:
                client.write_single_register(SLAVE, addr, target & 0xFFFF)
            except Exception as exc:  # noqa: BLE001
                say(f"  !! 写 330[{addr}] 异常: {exc}")
                continue
            time.sleep(0.08)
            # 2) 判据：镜像回读 == 目标（不看状态位）
            ok = False
            while time.time() - t0 < 45:
                time.sleep(0.5)
                if s16(rd(addr)[0]) == target:
                    ok = True
                    break
            say(f"  [AI{i}] {'OK' if ok else '!! 超时'}  用时 {time.time() - t0:.1f}s  "
                f"回读 330[{addr}]={s16(rd(addr)[0])}")

    hp = [s16(rd(st + OFF_HP1_IN_STATUS)[0]), s16(rd(st + OFF_HP2_IN_STATUS)[0])]
    say(f"  现在: 高压1={hp[0]} kPa ({pt.pt_temp(ref, hp[0]):.1f}C)"
        f"   高压2={hp[1]} kPa ({pt.pt_temp(ref, hp[1]):.1f}C)")
    client.close()

    if dry or watch <= 0:
        _write()
        return 0

    # ---- ST-Link 盯变频风机 ----
    say("")
    say("=== ST-Link 盯变频风机（机型1/类型2）===")
    from pyocd.core.helpers import ConnectHelper

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        say("!! 没找到 ST-Link")
        _write()
        return 1
    session.open()
    tgt = session.target
    if tgt.get_state() == tgt.State.HALTED:
        say("!! 进入时 HALTED —— 已 resume")
        tgt.resume()

    def r8(a: int) -> int:
        return tgt.read_memory_block8(a, 1)[0]

    def r32(a: int) -> int:
        v = tgt.read_memory_block8(a, 4)
        return v[0] | (v[1] << 8) | (v[2] << 16) | (v[3] << 24)

    say("   t(s) VfdOn  VfdHz  Load Unld Full  Comp  ChgSec")
    t0 = time.time()
    nxt_wd = 0.0
    prev = None
    while time.time() - t0 < watch:
        el = time.time() - t0
        if el >= nxt_wd:
            nxt_wd = el + 10
            if tgt.get_state() == tgt.State.HALTED:
                say(f"  [{el:5.1f}] !! HALTED —— resume")
                tgt.resume()
        cur = (r8(0x20000D01), r32(0x20000D30), r32(0x20000D48),
               r32(0x20000D4C), r32(0x20000D50), r8(0x20000DD4), r8(0x20000DD5),
               r32(0x20000D28))
        if cur != prev:
            say("  %5.1f %5d %6.1f %5d %4d %4d  %d,%d  %6d"
                % (el, cur[0], cur[1] / 10.0, cur[2], cur[3], cur[4], cur[5], cur[6], cur[7]))
            prev = cur
        time.sleep(0.25)

    if tgt.get_state() == tgt.State.HALTED:
        say("!! 结束 HALTED —— resume")
        tgt.resume()
    say(f"结束 state={tgt.get_state().name}")
    session.close()
    _write()
    return 0


def _write() -> None:
    p = pathlib.Path(__file__).resolve().parent / "bench_cond_temp.txt"
    p.write_text("\n".join(LINES) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
