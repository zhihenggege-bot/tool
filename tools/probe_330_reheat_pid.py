# -*- coding: utf-8 -*-
"""330 §3.6 再热/辅热/非热泵制热加减载 逐拍对账。

规格书 code/scratch_spec.txt §3.6：
    N(KR)=MIN(1,N(KR-1)+Z(KR))
    Z(KR)=KPRZ*BX/100*[E(KR)-E(KR-1)+T/TIRZ*E(KR)+KDRZ/T*(E(KR)-2E(KR-1)+E(KR-2))]
    当 -WDF/4 < E(KR) < WDF/4 时 Z=0
    E(KR-1)/E(KR-2) 无记录 ⇒ N=0, Z=0
    室内温度 > WD+WD/4 → 再热/辅热全关
    室内温度 < WD-WD/2 → 再热/辅热全开

参数下标（已逐个对着 User.h 核过）：
    N=[890] ReheatDemandDisp   E=[927] ReheatPidEDisp   Z=[928] ReheatPidZDisp
    WD=[739] ControlTempDisp   室内温度=[738] RealTempDisp   WDF=[120] RoomTempDiffSet
    KPRZ/TIRZ/KDRZ=[347]/[348]/[349]   T=[412]   SysStep=[709]
    方式[128] 制热方式  状态[942] ReheatPidStateDisp
    状态值: 0=OFF 1=WAIT_FULL_LOAD 2=INIT 3=REGULATING 4=DEADBAND 5=FORCE_FULL 6=FORCE_OFF 7=DEFROST

⚠ 跳拍检测：固件每拍才写一次 [928]Z/[890]N，"Z 或 N 变了"= 刚跳过一拍。
  固件**先写 Z 再写 N**，采样正好落在中间会看到"同一拍两个事件"，判据要用 ΔN==Z。

跑法： python.exe tools/probe_330_reheat_pid.py 180
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1
OUT = pathlib.Path(__file__).resolve().parent / "probe_330_reheat_pid.txt"

FAST = [890, 927, 928, 738]       # N, E, Z, 室内温度
CFG = [236, 709, 128, 738, 739, 120, 347, 348, 349, 412, 942]

STATE = {0: "OFF", 1: "WAIT_FULL_LOAD", 2: "INIT", 3: "REGULATING",
         4: "DEADBAND", 5: "FORCE_FULL", 6: "FORCE_OFF", 7: "DEFROST"}
WM = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排风", 5: "自动"}
HM = {0: "无", 1: "热泵制热", 2: "0-10V", 3: "1:2", 4: "1:2:4", 5: "可控硅"}

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def tdiv(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def bx10_of(n: int) -> int:
    if n <= 100:
        return 1
    if n <= 200:
        return 2
    if n <= 400:
        return 4
    if n <= 500:
        return 6
    return 10


class PidSim:
    """IndoorPidDemandStep 的忠实复刻。"""

    def __init__(self, n0: int = 0) -> None:
        self.n, self.res, self.h, self.valid = n0, 0, [0, 0, 0], 0

    def step(self, e, kp, ti, td, t):
        t, kp, ti, td = clamp(t, 1, 10), clamp(kp, 1, 100), clamp(ti, 1, 1000), clamp(td, 0, 1000)
        self.h[2], self.h[1], self.h[0] = self.h[1], self.h[0], e
        if self.valid < 2:
            self.valid += 1
            self.n, self.res = 0, 0
            return 0
        num = (self.h[0] - self.h[1]) * ti * t + t * t * self.h[0] \
            + td * ti * (self.h[0] - 2 * self.h[1] + self.h[2])
        scaled = tdiv(kp * bx10_of(self.n) * num * 1000, 10 * ti * t)
        acc = self.res + scaled
        z = tdiv(acc, 1000)
        self.res = acc - z * 1000
        self.n = clamp(self.n + z, 0, 1000)
        if (self.n == 0 and acc < 0) or (self.n == 1000 and acc > 0):
            self.res = 0
        return z


def main() -> int:
    import app as m

    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 180.0

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    def rd(addr):
        for _ in range(3):
            try:
                return s16(client.read_holding_registers(SLAVE, addr, 1)[0])
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        return None

    cfg = {a: rd(a) for a in CFG}
    say("=== 330 §3.6 再热/辅热/非热泵制热 逐拍对账 ===")
    say("模式[236]=%s  制热方式[128]=%s  SysStep[709]=%d"
        % (WM.get(cfg[236], cfg[236]), HM.get(cfg[128], cfg[128]), cfg[709]))
    say("KPRZ[347]=%d TIRZ[348]=%d KDRZ[349]=%d T[412]=%d WDF[120]=%.1fC"
        % (cfg[347], cfg[348], cfg[349], cfg[412], cfg[120] / 10.0))
    say("WD[739]=%.1fC  室内温度[738]=%.1fC" % (cfg[739] / 10.0, cfg[738] / 10.0))
    say()

    # 等运行态
    t0 = time.time()
    while time.time() - t0 < 300:
        ss = rd(709)
        if ss is None:
            time.sleep(0.5); continue
        if ss == 2:
            break
        if int(time.time() - t0) % 10 == 0:
            say("  …等 SysStep=2（当前 %s），已等 %.0fs" % (ss, time.time() - t0))
        time.sleep(1.0)
    else:
        say("✗ 300 秒内没进运行态，退出")
        client.close(); OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8"); return 1

    say("已进入运行态（SysStep=2），开始采样 %.0f 秒 …" % seconds)
    say()
    say("  拍 |    t | E(927) 室内(738) WD(739) | 实际Z 实际N | 期望Z 期望N | 状态     | 判定")
    say("     |      | 全关线 WD*1.25=%.1fC  全开线 WD*0.5=%.1fC"
        % (cfg[739] * 1.25 / 10.0, cfg[739] * 0.5 / 10.0))

    n0, z0 = rd(890), rd(928)
    if n0 is None or z0 is None:
        say("✗ 首读失败"); client.close(); return 1
    sim = PidSim(n0)
    prev_n, prev_z = n0, z0
    _e = rd(927)
    if _e is not None:
        sim.step(_e, cfg[347], cfg[348], cfg[349], cfg[412])

    beat = 0
    t1 = time.time()
    while time.time() - t1 < seconds:
        n, z, e, room = rd(890), rd(928), rd(927), rd(738)
        if None in (n, z, e, room):
            time.sleep(0.15); continue
        if n != prev_n or z != prev_z:
            ss = rd(709)
            if ss != 2:
                say("  SysStep 变 %s，停止采样" % ss); break
            wd = cfg[739]
            heat = "全关" if room * 4 > wd * 5 else ("全开" if room * 2 < wd else "PID")
            beat += 1
            expZ = sim.step(e, cfg[347], cfg[348], cfg[349], cfg[412])
            ok = "OK" if expZ == z else "Z✗"
            say("  %3d | %5.0f | %6d %8.1f %7.1f | %5d %5d | %5d %5d | %-9s | %s %s"
                % (beat, time.time() - t1, e, room / 10.0, wd / 10.0,
                   z, n, expZ, sim.n, STATE.get(rd(942), "?"), heat, ok))
            prev_n, prev_z = n, z
        time.sleep(0.15)

    say()
    say("结束（%d 拍）" % beat)
    client.close()
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
