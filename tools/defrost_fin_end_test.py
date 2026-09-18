"""一次跑两件事：**排他性**（外机1 也造请求）+ **翅片温度结束**。

背景 —— 要验「化霜结束原因①翅片温度达【化霜结束室外机翅片温度】」有个矛盾：
    开始条件④要求 `翅片 < 【化霜开始前翅片温度】`(默认 -2.0)
    结束条件①要求 `翅片 >= 【化霜结束室外机翅片温度】`(外机2 = 30.0)
两者不能同时成立。所以必须**先让化霜起来（翅片低），再在化霜过程中把翅片抬上去**。

做法：
  1. 设 外机1：翅片偏移 -> 保证显示远低于 -2.0；`[23]` 间隔 -> 15 分（和外机2 一致）
     -> 外机1 也会请求化霜，用于验排他性
  2. ST-Link 盯 **330**（`PSC316DefrostOwner` + 两台外机的 CompStatus/CanDefrost/DefrostSignal
     + 辅热），ST-Link 插 330 时才有这些
  3. 一旦看到 **外机2 的 CompStatus==4（除霜）**，立刻经 Modbus 把外机2 的翅片偏移抬到 ~32.0C
     -> 触发「翅片温度结束」，看它是不是**早于** 120 秒到时就把化霜结束掉

判据：`PSC316DefrostRunTime` 应 < 120 秒就结束；330 侧看外机2 的 CompStatus 4 -> 3 提前。

跑法：
    python.exe tools/defrost_fin_end_test.py --setup     # 只做外机1 的设置
    python.exe tools/defrost_fin_end_test.py --run 1800  # 盯 + 自动抬翅片
    python.exe tools/defrost_fin_end_test.py --restore   # 还原外机1/外机2 的偏移与 [23]
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
STATUS_BASE = 1550
STATUS_STEP = 70
DIAG_OFF = 42

TARGET = "stm32f407ze"
A_OWNER = 0x20000ECE
A_UNITWRITE = 0x20007858
A_UNITREAD = 0x200080C8
A_HEAT_DEMAND = 0x20000D18
W_STEP, W_DEFSIGNAL = 120, 16
R_STEP, R_COMPSTATUS, R_CANDEFROST = 196, 98, 106
PARAM_BASE = 0x200030C8
P_PIDSTATE = 942

# 台面原始值（2026-09-18 动手之前读到的），--restore 用
# ⚠ 外机2 的 gap23 原值是 **30**，不是 15 —— 15 是我改完之后的读数，一度记错。
#   取证：动手前 `set_316_gateway_param.py --unit 2 --list` 显示 [23] = 30。
ORIG = {
    1: {"fin1": 29, "fin2": 31, "gap23": 29},
    2: {"fin1": -172, "fin2": -177, "gap23": 30},
}
FIN1_CH, FIN2_CH = 1, 2          # 台面块里 +1/+2 = 翅片1/翅片2
GAP23 = 23

LOG: list[str] = []


def say(s: str = "") -> None:
    LOG.append(s)
    print(s, flush=True)


def write_out() -> None:
    (pathlib.Path(__file__).resolve().parent / "defrost_fin_end_test.txt").write_text(
        "\n".join(LOG) + "\n", encoding="utf-8")


def main() -> int:
    import app as m

    def opt(name, default=None):
        if name not in sys.argv:
            return default
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default

    mode = "run"
    for c in ("--setup", "--run", "--restore", "--status"):
        if c in sys.argv:
            mode = c[2:]
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(pos[0]) if pos else 1800.0

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

    def gw_write(addr, target, tag):
        t0 = time.time()
        try:
            client.write_single_register(SLAVE, addr, target & 0xFFFF)
        except Exception as exc:  # noqa: BLE001
            say(f"    !! [{tag}] 写 {addr} 异常: {exc}")
            return False
        time.sleep(0.08)
        while time.time() - t0 < 45:
            time.sleep(0.5)
            if s16(rd(addr)[0]) == target:
                say(f"    [{tag}] OK {time.time() - t0:.1f}s  [{addr}]={target}")
                return True
        say(f"    !! [{tag}] 超时 [{addr}] 回读={s16(rd(addr)[0])} 期望={target}")
        return False

    def wait_slot(unit):
        gw = GW_BASE + (unit - 1) * GW_STEP
        deadline = time.time() + 30
        while time.time() < deadline:
            if s16(rd(gw + DIAG_OFF + 1)[0]) != 1:
                return
            time.sleep(0.35)

    # ---------- 读当前 ----------
    def dump():
        say("--- 当前 ---")
        for u in (1, 2):
            gw = GW_BASE + (u - 1) * GW_STEP
            comp = COMPACT_BASE + (u - 1) * 16
            st = STATUS_BASE + (u - 1) * STATUS_STEP
            say("  外机%d 环温=%.1fC 偏移[环,翅1,翅2]=%s  [21]翅片起=%.1f [23]间隔=%d [25]翅片止=%.1f"
                % (u, s16(rd(st + 2)[0]) / 10.0,
                   [s16(x) for x in rd(comp, 3)],
                   s16(rd(gw + 21)[0]) / 10.0, s16(rd(gw + 23)[0]),
                   s16(rd(gw + 25)[0]) / 10.0))

    dump()

    if mode == "restore":
        say(">>> 还原")
        for u in (1, 2):
            gw = GW_BASE + (u - 1) * GW_STEP
            comp = COMPACT_BASE + (u - 1) * 16
            wait_slot(u)
            gw_write(comp + FIN1_CH, ORIG[u]["fin1"], "外机%d 翅片1偏移" % u)
            wait_slot(u)
            gw_write(comp + FIN2_CH, ORIG[u]["fin2"], "外机%d 翅片2偏移" % u)
            wait_slot(u)
            gw_write(gw + GAP23, ORIG[u]["gap23"], "外机%d [23]间隔" % u)
        dump()
        client.close()
        write_out()
        return 0

    if mode == "setup":
        say(">>> 设外机1：翅片压到远低于 -2.0，[23] 改 15 分")
        comp = COMPACT_BASE + 0 * 16
        # 直接给一个大负偏移，保证显示远低于 -2.0（不知道真实值也能保证）
        wait_slot(1)
        gw_write(comp + FIN1_CH, -300, "外机1 翅片1偏移")
        wait_slot(1)
        gw_write(comp + FIN2_CH, -300, "外机1 翅片2偏移")
        wait_slot(1)
        gw_write(GW_BASE + GAP23, 15, "外机1 [23]间隔")
        dump()
        client.close()
        write_out()
        return 0

    # ---------- run：盯 330 + 到点抬翅片 ----------
    from pyocd.core.helpers import ConnectHelper
    session = ConnectHelper.session_with_chosen_probe(
        target_override=TARGET, options={"frequency": 1000000, "connect_mode": "attach"})
    if session is None:
        say("!! 没找到 ST-Link（run 模式需要 ST-Link 插在 330）")
        client.close()
        write_out()
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

    say(">>> 盯 330：Owner / 两台外机 CS,CD,DS / 辅热。看到外机2 除霜就把它的翅片抬到 32.0C")
    say("  t | Owner | u1 CS/CD/DS | u2 CS/CD/DS | AODem PID | 动作")
    t0 = time.time()
    prev = None
    raised = False
    nxt_wd = 0.0
    while time.time() - t0 < seconds:
        el = time.time() - t0
        if el >= nxt_wd:
            nxt_wd = el + 10.0
            if tgt.get_state() == tgt.State.HALTED:
                say(f"  [{el:6.1f}] !! HALTED —— resume")
                tgt.resume()
        try:
            owner = r8(A_OWNER)
            u = []
            for k in (1, 2):
                cs = [r16m(A_UNITREAD + k * R_STEP + R_COMPSTATUS + 2 * i) for i in range(2)]
                cd = [r16m(A_UNITREAD + k * R_STEP + R_CANDEFROST + 2 * i) for i in range(2)]
                ds = [r16m(A_UNITWRITE + k * W_STEP + W_DEFSIGNAL + 2 * i) for i in range(2)]
                u.append((cs, cd, ds))
            hd = r32(A_HEAT_DEMAND)
            pid = ps(P_PIDSTATE)
        except Exception as exc:  # noqa: BLE001
            say(f"  [{el:6.1f}] !! 读失败: {exc}")
            time.sleep(0.2)
            continue
        act = ""
        # 外机2 进除霜 -> 抬翅片（只做一次）
        if (not raised) and (4 in u[1][0]):
            raised = True
            act = "外机2 除霜 -> 抬翅片"
            say(f"  [{el:6.1f}] {act}")
            comp = COMPACT_BASE + 1 * 16
            st1 = STATUS_BASE + 1 * STATUS_STEP
            # 目标显示 32.0C：new = old + (320 - 当前显示)
            for ch, nm in ((FIN1_CH, "翅片1"), (FIN2_CH, "翅片2")):
                cur_off = s16(rd(comp + ch)[0])
                # 当前显示只能从 316 读；这里用「上次设的显示」+ 偏移差推算不可靠，
                # 所以改用保守做法：直接按目标显示 = 当前偏移 + delta 的等价式不可得时，
                # 用固定抬升量（+400 = +40.0C），保证从 -8.0 抬到 +32.0。
                new_off = cur_off + 400
                wait_slot(2)
                gw_write(comp + ch, new_off, "外机2 %s 抬到 +32C" % nm)
                act = ""
        key = (owner, tuple(tuple(x) for x in u), hd, pid)
        if key != prev or act:
            say("  %6.0f %5d  %s  %s  %5d %3d  %s"
                % (el, owner,
                   "%s/%s/%s" % (u[0][0], u[0][1], u[0][2]),
                   "%s/%s/%s" % (u[1][0], u[1][1], u[1][2]),
                   hd, pid, act))
            prev = key
        time.sleep(0.1)

    if tgt.get_state() == tgt.State.HALTED:
        say("!! 结束 HALTED —— resume")
        tgt.resume()
    say(f"结束 state={tgt.get_state().name}  抬翅片={'已做' if raised else '没触发'}")
    session.close()
    client.close()
    dump()
    write_out()
    return 0


if __name__ == "__main__":
    sys.exit(main())
