"""A5 验证：复位后「风机没开 + 冷凝>45」启动瞬间是不是满频。

规格书：**若风机没开，冷凝温度大于45度满频。**

V12.12 的改动点：`OutdoorFanPrestartVfd()` 里也判冷凝温度
    OutdoorVfdSpeed = (OutdoorCondTempMax() > 450) ? MaxSpeed : MinSpeed;

关键在**抓住启动那一瞬间**，所以复位和高频采样必须在同一个进程里做
（两个进程抢同一个 ST-Link 会冲突）。采样 10Hz，VfdSpeed 一有变化就记。

跑法：
    python.exe tools/verify_a5_prestart_full_speed.py [采样秒数，默认120]
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))
import pt_tables as pt  # noqa: E402

PARAM_BASE = 0x2000164A
SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0

A_VFD_ON = 0x20000D01
A_VFD_SPEED = 0x20000D30
A_VFD_LOAD = 0x20000D48
A_VFD_UNLOAD = 0x20000D4C
A_VFD_FULL = 0x20000D50
A_NOCOMP = 0x20000D2C
A_CHGSEC = 0x20000D28
A_STOP0 = 0x20000DA8
A_COMP = 0x20000DD4
A_OUTPUT = 0x200000D4

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    def connect():
        ss = ConnectHelper.session_with_chosen_probe(
            target_override="stm32f103rc",
            options={"frequency": 1000000, "connect_mode": "attach"},
        )
        ss.open()
        tt = ss.target
        if tt.get_state() == tt.State.HALTED:
            say("!! 连接时 HALTED —— 已 resume")
            tt.resume()
        return ss, tt

    session, tgt = connect()

    def r8(a):
        return tgt.read_memory_block8(a, 1)[0]

    def r16(i):
        v = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        x = v[0] | (v[1] << 8)
        return x - 0x10000 if x & 0x8000 else x

    def r32(a):
        v = tgt.read_memory_block8(a, 4)
        return v[0] | (v[1] << 8) | (v[2] << 16) | (v[3] << 24)

    ref = r16(39)
    if ref not in (0, 1, 2, 3):
        ref = 3
    off0, off1 = r16(310), r16(322)
    hp1, hp2 = r16(1443), r16(1445)
    cond = max(pt.pt_temp(ref, hp1), pt.pt_temp(ref, hp2))
    say("=== 复位前 ===")
    say(f"  316 版本 = {[r16(i) for i in range(1000, 1006)]}   <- 需要 12,12")
    say(f"  机型={r16(165)} 风机类型={r16(166)} 制冷剂={pt.REFRIGERANT_NAMES[ref]}")
    say(f"  AI偏移 AI0={off0} AI1={off1}   高压1={hp1}({pt.pt_temp(ref, hp1):.1f}C) 高压2={hp2}({pt.pt_temp(ref, hp2):.1f}C)"
        f"  -> 冷凝={cond:.1f}C")
    say(f"  VfdOn={r8(A_VFD_ON)} VfdSpeed={r32(A_VFD_SPEED) / 10.0:.1f}Hz"
        f"  Comp={r8(A_COMP)},{r8(A_COMP + 1)}  NoCompSec={r32(A_NOCOMP)}")
    if cond <= 45.0:
        say()
        say(f"!! 冷凝 {cond:.1f}C 没有 >45，这条用例的前提不成立。")
        say("   先用 bench_cond_temp.py 把冷凝推到 47.0C 再来。")
        session.close()
        _write()
        return 2

    # ---- 复位 ----
    say()
    say(">>> tgt.reset()（复位并运行）")
    tgt.reset()
    t0 = time.time()

    # ---- 立刻高频采样，抓启动瞬间 ----
    say()
    say("=== 复位后 10Hz 采样（只记变化）===")
    say("   t(s)  VfdOn  VfdHz  Comp   NoCmp  ChgSec  Stop0  Load Unld Full  Y02 Y03 Y07")
    prev = None
    first_on = None
    started = False
    next_wd = 0.0
    while time.time() - t0 < SECONDS:
        el = time.time() - t0
        if el >= next_wd:
            next_wd = el + 10.0
            try:
                if tgt.get_state() == tgt.State.HALTED:
                    say(f"  [{el:5.1f}] !! HALTED —— resume")
                    tgt.resume()
            except Exception:  # noqa: BLE001
                pass
        try:
            out = [r8(A_OUTPUT + i) for i in range(8)]
            cur = (r8(A_VFD_ON), r32(A_VFD_SPEED), r8(A_COMP), r8(A_COMP + 1),
                   r32(A_NOCOMP), r32(A_CHGSEC), r32(A_STOP0),
                   r32(A_VFD_LOAD), r32(A_VFD_UNLOAD), r32(A_VFD_FULL),
                   out[2], out[3], out[7])
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:5.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue
        if cur != prev:
            say("  %5.1f %6d %6.1f  %d,%d %6d %7d %6d %5d %4d %4d  %d   %d   %d"
                % ((el, cur[0], cur[1] / 10.0, cur[2], cur[3]) + cur[4:]))
            if cur[0] == 1 and not started:
                started = True
                first_on = (el, cur[1] / 10.0)
            prev = cur
        time.sleep(0.1)

    say()
    if first_on:
        el, hz = first_on
        say(f">>> 复位后首次看到风机在转：t={el:.1f}s  VfdSpeed={hz:.1f}Hz")
        say(f"    预期（V12.12）：冷凝>45 时应为 50.0Hz（满频）；V12.11 实测是 20.0Hz")
        say(f"    判定：{'[通过] 符合规格书' if hz >= 49.0 else '[不通过] 不符 —— 给的是 %.1fHz' % hz}")
    else:
        say(f">>> {SECONDS:.0f} 秒内没看到风机启动（VfdOn 一直为 0）")

    try:
        if tgt.get_state() == tgt.State.HALTED:
            say("!! 结束 HALTED —— resume")
            tgt.resume()
        say(f"结束 state={tgt.get_state().name}")
    except Exception:  # noqa: BLE001
        pass
    session.close()
    _write()
    return 0


def _write() -> None:
    (pathlib.Path(__file__).resolve().parent / "verify_a5_prestart_full_speed.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
