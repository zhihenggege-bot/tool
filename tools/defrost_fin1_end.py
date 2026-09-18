"""外机侧（ST-Link 插 316）：盯化霜 + 在化霜中**只抬「翅片1」**，验两件事。

  ① 化霜结束原因①「翅片温度达【化霜结束室外机翅片温度】」
  ② 规格书「**对应**压缩机关闭」—— 只抬翅片1 时，应**只有系统0 关**，
     系统1 继续到 `RunTime[1]` 走满 MaxDefrostTime

判据：
    系统0: FinTemp[0] >= [25]  ->  Ended[0]=1, Comp[0]=0   （应早于 120 秒）
    系统1: FinTemp[1] 仍在 -8  ->  Ended[1]=0, Comp[1]=1   （应走满）
    两者都 End -> DefrostState 1->2，再过 60 秒 -> 0

做法：ST-Link 盯 316 的 `PSC316DefrostState`；一看到 0->1（化霜开始），
      经 Modbus 把**外机2 的翅片1 偏移** +400（显示从 -8.0 抬到 ≈ +32.0C），
      **不动翅片2**。

跑法：
    python.exe tools/defrost_fin1_end.py 1500
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT = "COM6"
SLAVE = 1
COMPACT_BASE = 2534
GW_BASE = 1830
GW_STEP = 48
DIAG_OFF = 42
UNIT = 2                      # 默认外机2；--unit N 可覆盖
FIN1_CH = 1                   # 台面块 +1 = 翅片1

PARAM_BASE = 0x2000164A
A_DEF_STATE = 0x20000DF0
A_DEF_TIMED = 0x20000DF1
A_DEF_ELIG = 0x20000DF6
A_DEF_ENDED = 0x20000DF8
A_DEF_STARTED = 0x20000DFA
A_DEF_RUNTIME = 0x20000E10
A_DEFSTATETIME = 0x20000E00
A_INDEFROST = 0x20000DB0
A_COMP = 0x20000DD4
A_FAN = 0x20000DDE
A_FOUR = 0x20000DD9
A_OUTPUT = 0x200000D4
A_DEFGAP = 0x200026A0
A_DEFCOMP0 = 0x200026D4
A_FINLOW = 0x2000274C
P_ENVI, P_FIN1, P_FIN2 = 1422, 1431, 1432
P_330EN1, P_330EN2 = 1400, 1403

LOG: list[str] = []


def say(s: str = "") -> None:
    LOG.append(s)
    print(s, flush=True)


def write_out() -> None:
    (pathlib.Path(__file__).resolve().parent / "defrost_fin1_end.txt").write_text(
        "\n".join(LOG) + "\n", encoding="utf-8")


def main() -> int:
    import app as m
    from pyocd.core.helpers import ConnectHelper

    global UNIT
    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 1500.0
    if "--unit" in sys.argv:
        UNIT = int(sys.argv[sys.argv.index("--unit") + 1])

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

    comp = COMPACT_BASE + (UNIT - 1) * 16
    gw = GW_BASE + (UNIT - 1) * GW_STEP

    def write_off(addr, target, tag):
        deadline = time.time() + 30
        while time.time() < deadline:
            if s16(rd(gw + DIAG_OFF + 1)[0]) != 1:
                break
            time.sleep(0.35)
        t0 = time.time()
        try:
            client.write_single_register(SLAVE, addr, target & 0xFFFF)
        except Exception as exc:  # noqa: BLE001
            say(f"    !! [{tag}] 写异常: {exc}")
            return
        time.sleep(0.08)
        while time.time() - t0 < 45:
            time.sleep(0.5)
            if s16(rd(addr)[0]) == target:
                say(f"    [{tag}] OK {time.time() - t0:.1f}s  [{addr}]={target}")
                return
        say(f"    !! [{tag}] 超时 [{addr}] 回读={s16(rd(addr)[0])}")

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"})
    if session is None:
        say("!! 没找到 ST-Link")
        write_out()
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

    def r16(i):
        b = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        v = b[0] | (b[1] << 8)
        return v - 0x10000 if v & 0x8000 else v

    def r32(a):
        b = tgt.read_memory_block8(a, 4)
        return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)

    say("=== 外机%d 化霜：只抬翅片1 -> 验「对应压缩机关闭」===" % UNIT)
    say(f"版本={[r16(1000 + i) for i in range(6)]}  机型={r16(165)} 风机类型={r16(166)}")
    say(f"[25]化霜结束翅片温度 = %.1fC   [26]环温>0化霜时间 = %d 分"
        % (r16(165 + 25) / 10.0, r16(165 + 26)))
    say(f"翅片1 偏移 = {s16(rd(comp + FIN1_CH)[0])}   翅片1 显示 = {r16(P_FIN1) / 10.0:.1f}C")
    say()
    say("  t | St Tmd InD | Elig End Strt | DefRT | StateT | Comp | Fan Four |"
        " 环温 翅片1|2 | RT0 RT1 | 动作")
    prev = None
    t0 = time.time()
    raised = False
    while time.time() - t0 < seconds:
        el = time.time() - t0
        if tgt.get_state() == tgt.State.HALTED:
            say(f"  [{el:6.1f}] !! HALTED —— resume")
            tgt.resume()
        try:
            st = r8(A_DEF_STATE)
            cur = (st, r8(A_DEF_TIMED), r8(A_INDEFROST),
                   tuple(r8n(A_DEF_ELIG, 2)), tuple(r8n(A_DEF_ENDED, 2)),
                   tuple(r8n(A_DEF_STARTED, 2)), tuple(r8n(A_COMP, 2)),
                   tuple(r8n(A_FAN, 2)), tuple(r8n(A_FOUR, 2)))
            rt = [r32(A_DEF_RUNTIME + 4 * i) for i in range(2)]
            statet = r32(A_DEFSTATETIME)
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:6.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue
        act = ""
        if (not raised) and st == 1:
            raised = True
            act = "化霜开始 -> 只抬翅片1"
            say(f"  [{el:6.1f}] {act}")
            # ⚠ 抬升量必须按【化霜结束室外机翅片温度】[25] 算，不能写死 +40C。
            #   外机1 的 [25] = 39.0C（外机2 是 30.0C）—— 第一次写死 +400 只抬到
            #   18.0C，没越过 39.0，结果走了"到时"结束，白跑一轮。
            #   new_offset = old + (阈值 + 2.0C 余量 - 当前显示)
            thr = r16(165 + 25)                    # 0.1C
            disp = r16(P_FIN1)                     # 0.1C
            old = s16(rd(comp + FIN1_CH)[0])
            delta = (thr + 20) - disp
            say(f"      [25]={thr / 10.0:.1f}C  当前显示={disp / 10.0:.1f}C"
                f"  -> 抬 {delta / 10.0:+.1f}C")
            write_off(comp + FIN1_CH, old + delta, "翅片1 抬过阈值")
            act = ""
            say(f"      抬后: 翅片1 显示 = {r16(P_FIN1) / 10.0:.1f}C  "
                f"翅片2 显示 = {r16(P_FIN2) / 10.0:.1f}C（应保持 -8）")
        if cur != prev or act:
            say("  %6.1f  %2d %3d %3d  %s %s %s  %s %5d  %s  %s %s  %5.1f %5.1f|%5.1f  %s %s  %s"
                % (el, cur[0], cur[1], cur[2], cur[3], cur[4], cur[5], rt, statet,
                   cur[6], cur[7], cur[8],
                   r16(P_ENVI) / 10.0, r16(P_FIN1) / 10.0, r16(P_FIN2) / 10.0,
                   rt, [r16(P_330EN1), r16(P_330EN2)], act))
            prev = cur
        time.sleep(0.1)

    if tgt.get_state() == tgt.State.HALTED:
        say("!! 结束 HALTED —— resume")
        tgt.resume()
    say(f"结束 state={tgt.get_state().name}  抬翅片={'已做' if raised else '没触发'}")
    session.close()
    client.close()
    write_out()
    return 0


if __name__ == "__main__":
    sys.exit(main())
