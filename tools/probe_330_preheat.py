"""330 预热动态记录（规格书 3.7）—— 纯 Modbus，不占 ST-Link。

规格书 3.7 两种方式（下标已对着 User.h 逐个核过）：
  方式1 插入法（[374]=0）：用【新风温度】[512]
      (PreHeatControl UserAction.c:3112-3119)
      [512] <= 满载温度[357] -> N = 1000
      [512] >= 开启温度[356] -> N = 0
      中间 -> ( [356] - [512] ) * 1000 / ( [356] - [357] )
  方式2 PID（[374]=1 且 [333]==HEAT_OUTPUT_AO=1）：用【预热后温度】[513]
      (UserAction.c:3084-3111 -> IndoorPidDemandStep UserAction.c:748-831)
      E = YWD[375] - [513]              死区 |E|*4 < YWDF[376] -> Z=0
      BX = IndoorDemandBx10(N)：N<=100→1, <=200→2, <=400→4, <=500→6, else 10
      num = (E0-E1)*TI*T + T*T*E0 + KD*TI*(E0-2*E1+E2)
      Z   = KP*BX*num / (10*TI*T)        （带 1/1000 余数累加器，不丢小数）
      N  += Z，限幅 0..1000
      T = [412] PidAdjustTimeSet1；每 t*10 个 100ms 才走一拍；前 2 拍 N=0

注入链（写显示值无效，每扫描被覆写）：
      NTC[i] = round(真实温度*10) + [484+i]        NTC16bit.c:262
      [512] = AI[7] = NTC[2]  ← 注入 [493]
      [513] = AI[8] = NTC[3]  ← 注入 [492]
      ⇒ 真实温度 = 显示值 - 偏移；**改偏移是叠加不是替换**

参数下标：
  [333] PreheatModeSet(1=AO)  [374] PreheatCtrlModeSet(0=插入法 1=PID)
  [356] 开启温度  [357] 满载温度  [375] YWD  [376] YWDF
  [350] KPY  [351] TIY  [352] KDY  [412] T  [452] 介质
  [511]室内 [512]新风 [513]预热后  [891]N  [929]E  [930]Z  [968]预热故障锁存  [709]SysStep
  [492] NTC3 偏移(预热后)   [493] NTC2 偏移(新风)

跑法： python.exe tools/probe_330_preheat.py 600
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1

P_WMODE, P_SYSSTEP = 236, 709
P_LATCH = 968
P_EN, P_MODE, P_MEDIUM = 333, 374, 452
P_START, P_FULL = 356, 357
P_YWD, P_YWDF = 375, 376
P_KPY, P_TIY, P_KDY, P_T = 350, 351, 352, 412
P_ROOM, P_FRESH, P_AFTER = 511, 512, 513
P_OFF_AFTER, P_OFF_FRESH = 492, 493
P_DEMAND, P_E, P_Z = 891, 929, 930

WM = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排风", 5: "自动"}
LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_330_preheat.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


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


def tdiv(a: int, b: int) -> int:
    """C 的整数除法：向零截断（不是 Python 的向下取整）。"""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else (hi if v > hi else v)


class PidSim:
    """IndoorPidDemandStep 的忠实复刻（含 1/1000 余数累加器）。"""

    def __init__(self) -> None:
        self.n = 0
        self.res = 0            # residualMilli
        self.h = [0, 0, 0]      # history[0..2]
        self.valid = 0

    def reset(self) -> None:
        self.__init__()

    def step(self, e: int, kp: int, ti: int, td: int, ywdf: int, t: int) -> int:
        t = clamp(t, 1, 10)
        kp = clamp(kp, 1, 100)
        ti = clamp(ti, 1, 1000)
        td = clamp(td, 0, 1000)
        if ywdf < 0:
            ywdf = 0
        self.h[2], self.h[1], self.h[0] = self.h[1], self.h[0], e
        if self.valid < 2:
            self.valid += 1
            self.n = 0
            self.res = 0
            return 0
        if abs(e) * 4 < ywdf:
            self.n = clamp(self.n, 0, 1000)
            self.res = 0
            return 0
        bx = bx10_of(self.n)
        num = (self.h[0] - self.h[1]) * ti * t \
            + t * t * self.h[0] \
            + td * ti * (self.h[0] - 2 * self.h[1] + self.h[2])
        den = 10 * ti * t
        scaled = tdiv(kp * bx * num * 1000, den)
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
    seconds = float(nums[0]) if nums else 600.0

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    regs = [P_WMODE, P_SYSSTEP, P_LATCH, P_EN, P_MODE, P_MEDIUM, P_START,
            P_FULL, P_YWD, P_YWDF, P_KPY, P_TIY, P_KDY, P_T,
            P_ROOM, P_FRESH, P_AFTER, P_OFF_AFTER, P_OFF_FRESH,
            P_DEMAND, P_E, P_Z]

    def rd_many(addrs):
        out = {}
        for a in addrs:
            for _ in range(3):
                try:
                    out[a] = client.read_holding_registers(SLAVE, a, 1)[0]
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.2)
            out.setdefault(a, -1)
        return {k: (v - 0x10000 if v & 0x8000 else v) for k, v in out.items()}

    v = rd_many(regs)
    say("=== 330 预热动态记录（规格书 3.7）===")
    say("SysStep[709]=%d  模式[236]=%s  预热锁存[968]=%d"
        % (v[P_SYSSTEP], WM.get(v[P_WMODE], v[P_WMODE]), v[P_LATCH]))
    say("使能[333]=%d(1=AO)  控制方式[374]=%d(0=插入法1=PID)  介质[452]=%d"
        % (v[P_EN], v[P_MODE], v[P_MEDIUM]))
    say("开启温度[356]=%.1fC  满载温度[357]=%.1fC  YWD[375]=%.1fC  YWDF[376]=%.1fC"
        % (v[P_START] / 10.0, v[P_FULL] / 10.0, v[P_YWD] / 10.0, v[P_YWDF] / 10.0))
    say("KPY[350]=%d TIY[351]=%d KDY[352]=%d T[412]=%d" %
        (v[P_KPY], v[P_TIY], v[P_KDY], v[P_T]))
    say("注入偏移: [493]新风=%d(%.1fC)  [492]预热后=%d(%.1fC)"
        % (v[P_OFF_FRESH], v[P_OFF_FRESH] / 10.0,
           v[P_OFF_AFTER], v[P_OFF_AFTER] / 10.0))
    say("  真实值 = 显示 - 偏移:  新风真实=%.1fC  预热后真实=%.1fC"
        % ((v[P_FRESH] - v[P_OFF_FRESH]) / 10.0,
           (v[P_AFTER] - v[P_OFF_AFTER]) / 10.0))
    say()
    say("   t | Sys 方式 | 新风  预热后 (真实) | E(929) | N(891) BX Z(930) | 期望N 期望Z | 备注")
    prev = None
    sim = PidSim()
    t0 = time.time()
    last_mode = None
    while time.time() - t0 < seconds:
        el = time.time() - t0
        v = rd_many(regs)
        ss, mode = v[P_SYSSTEP], v[P_MODE]
        fresh, after = v[P_FRESH], v[P_AFTER]
        N, E, Z = v[P_DEMAND], v[P_E], v[P_Z]
        if mode != last_mode:
            sim.reset()
            last_mode = mode
        note = ""

        if mode == 1:
            # 方式2：PID。只在 SysStep==2 且制热时函数才跑
            if ss == 2 and v[P_WMODE] == 1 and v[P_EN] == 1 and v[P_LATCH] == 0:
                expZ = sim.step(E, v[P_KPY], v[P_TIY], v[P_KDY], v[P_YWDF], v[P_T])
            else:
                expZ = 0
            expN, bx = sim.n, bx10_of(sim.n)
            note = "PID"
            if abs(E) * 4 < v[P_YWDF]:
                note, expZ, expN = "死区", 0, N
        else:
            # 方式1：插入法
            st, fl = v[P_START], v[P_FULL]
            if ss == 2 and v[P_WMODE] == 1 and v[P_EN] == 1 and v[P_LATCH] == 0:
                if fresh <= fl:
                    expN = 1000
                elif fresh >= st:
                    expN = 0
                elif st > fl:
                    expN = (st - fresh) * 1000 // (st - fl)
                else:
                    expN = 0
            else:
                expN = 0
            bx, expZ = 0, 0
            note = "插入法"

        key = (ss, mode, fresh, after, N, E, Z)
        if key != prev:
            say("  %5.0f | %2d %4s | %5.1f %6.1f (%5.1f) | %5d | %5d %3d %5d | %6d %6d | %s"
                % (el, ss, note, fresh / 10.0, after / 10.0,
                   (after - v[P_OFF_AFTER]) / 10.0,
                   E, N, bx, Z, expN, expZ, ""))
            prev = key
        time.sleep(0.5)

    say("结束")
    client.close()
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
