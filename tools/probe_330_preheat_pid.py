# -*- coding: utf-8 -*-
"""330 预热后温度 PID（规格书 3.7 方式2）逐拍对账。

⚠ 为什么不用现成的 probe_330_preheat.py：那个脚本**每个采样点都推一次 sim**
   （time.sleep(0.5) 里 sim.step() 一次），而固件每 T*10 个 100ms 才走一拍
   （[412]=5 ⇒ 5 秒一拍）。PID 模式下 sim 会快 10 倍，对不上账。
   本脚本按**检测到的真实跳拍**驱动 sim。

固件侧（UserAction.c IndoorPidDemandStep）：
    count 计满 t*10 个 100ms 才走一拍
    num = (E0-E1)*ti*t + t*t*E0 + td*ti*(E0-2E1+E2)
    z   = kp*bx10*num*1000 / (10*ti*t)        （带 1/1000 余数累加器）
    N  += z, 限幅 0..1000

跳拍检测：固件每拍才写一次 [930] Z 和 [891] N，所以"Z 或 N 变了"= 刚跳过一拍。
    ⚠ 若连续多拍 Z 都不变（死区），检测不到跳拍 —— 此时 N 也不动，
      对 N 的核对无影响；但 sim 的 history 会少推，E0-E1 项会偏。
      本场景 KDY=0，微分项为 0，影响仅限比例项的 E0-E1。

跑法： python.exe tools/probe_330_preheat_pid.py 120
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1
OUT = pathlib.Path(__file__).resolve().parent / "probe_330_preheat_pid.txt"

FAST = [891, 929, 930, 513]          # N, E, Z, 预热后温度 —— 高频
CFG = [333, 374, 709, 375, 376, 412, 350, 351, 352, 512, 513, 968]

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def tdiv(a: int, b: int) -> int:
    """C 的整数除法：向零截断。"""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def clamp(v: int, lo: int, hi: int) -> int:
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

    def __init__(self) -> None:
        self.n = 0
        self.res = 0
        self.h = [0, 0, 0]
        self.valid = 0

    def step(self, e: int, kp: int, ti: int, td: int, t: int) -> int:
        t = clamp(t, 1, 10)
        kp = clamp(kp, 1, 100)
        ti = clamp(ti, 1, 1000)
        td = clamp(td, 0, 1000)
        self.h[2], self.h[1], self.h[0] = self.h[1], self.h[0], e
        if self.valid < 2:
            self.valid += 1
            self.n = 0
            self.res = 0
            return 0
        num = (self.h[0] - self.h[1]) * ti * t \
            + t * t * self.h[0] \
            + td * ti * (self.h[0] - 2 * self.h[1] + self.h[2])
        den = 10 * ti * t
        scaled = tdiv(kp * bx10_of(self.n) * num * 1000, den)
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
    seconds = float(nums[0]) if nums else 120.0

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    def rd(addr: int):
        """读失败返回 None —— 绝不能返回 -1：-1 是 Z/E 的合法值，会被当成真数据。"""
        for _ in range(3):
            try:
                return s16(client.read_holding_registers(SLAVE, addr, 1)[0])
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        return None

    cfg = {a: rd(a) for a in CFG}
    say("=== 330 预热 PID 逐拍对账 ===")
    say("SysStep[709]=%d  预热输出方式[333]=%d(1=AO 4=SCR)  预热控制方式[374]=%d(0=插入 1=PID)  锁存[968]=%d"
        % (cfg[709], cfg[333], cfg[374], cfg[968]))
    say("YWD[375]=%.1fC  YWDF[376]=%.1fC  T[412]=%d秒  KPY[350]=%d TIY[351]=%d KDY[352]=%d"
        % (cfg[375] / 10.0, cfg[376] / 10.0, cfg[412], cfg[350], cfg[351], cfg[352]))
    say("新风[512]=%.1fC  预热后[513]=%.1fC" % (cfg[512] / 10.0, cfg[513] / 10.0))
    say()

    if cfg[374] != 1 or cfg[333] not in (1, 4):
        say("⚠ 当前不是 PID 生效状态（需 [374]=1 且 [333]=1 或 4），下面只是记录。")
    if cfg[968] != 0 or cfg[709] != 2:
        say("⚠ SysStep/锁存不满足，PreHeatControl 会走提前返回分支。")
    say()

    sim = PidSim()
    say("  拍 |    t | E(929) 预热后(513) | 实际Z 实际N | 期望Z 期望N | 判定")
    prev_n, prev_z = rd(891), rd(930)
    if prev_n is None or prev_z is None:
        say("✗ 首读失败，退出")
        client.close()
        return 1
    _e = rd(929)
    if _e is not None:
        sim.step(_e, cfg[350], cfg[351], cfg[352], cfg[412])   # 首拍喂入，使 valid 计数与固件同步
    beat = 0
    t0 = time.time()
    while time.time() - t0 < seconds:
        n, z, e, after = rd(891), rd(930), rd(929), rd(513)
        if n is None or z is None or e is None or after is None:
            time.sleep(0.15)
            continue
        if n != prev_n or z != prev_z:
            beat += 1
            expZ = sim.step(e, cfg[350], cfg[351], cfg[352], cfg[412])
            expN = sim.n
            ok = "OK" if (expZ == z and expN == n) else \
                 ("Z✓N✗" if expZ == z else ("Z✗N✓" if expN == n else "✗"))
            say("  %3d | %5.0f | %6d %8.1f | %5d %5d | %5d %5d | %s"
                % (beat, time.time() - t0, e, after / 10.0, z, n, expZ, expN, ok))
            prev_n, prev_z = n, z
        time.sleep(0.15)

    say()
    say("结束（%d 拍）" % beat)
    client.close()
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
