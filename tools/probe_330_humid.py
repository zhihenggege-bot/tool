"""330 加湿 PID 动态记录（规格书 3.8）—— **纯 Modbus**，不占 ST-Link。

规格书 3.8：
    N(KS) = MIN(1, N(KS-1) + Z(KS))
    Z(KS) = KPS*BX/100*[E(KS)-E(KS-1) + T/TIS*E(KS) + KDS/T*(E(KS)-2E(KS-1)+E(KS-2))]
    -SDF/4 < E < SDF/4 -> Z = 0
    E(K-1)/E(K-2) 无记录 -> N(KS-1)=0, Z=0
    BX 按 N(KS-1) 分档: (0,0.1]->0.1  (0.1,0.2]->0.2  (0.2,0.4]->0.4  (0.4,0.5]->0.6  (0.5,1]->1

代码 `IndoorPidDemandStep()`（UserAction.c:748）：
    z = kp * bx10 * num / (10*ti*t)     num/(ti*t) = (E0-E1) + (t/ti)*E0 + (td/t)*(...)
    bx10 = IndoorDemandBx10(N)          = BX*10
    demand = clamp(demand + z, 0, 1000) （0~1000 对应规格书的 0~1）
    ⚠ 那个 /10 是 0.1 单位补偿：HumiditySet/HumiditySensorAI1Disp 都是 x0.1%RH

跑法： python.exe tools/probe_330_humid.py 600
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1

P_T = 412          # PidAdjustTimeSet1
P_KPS, P_TIS, P_KDS = 353, 354, 355
P_SDF = 361        # HumidityDiffSet
P_SET = 162        # HumiditySet         x0.1%RH
P_SENS = 501       # HumiditySensorAI1Disp
P_SYSSTEP = 709
P_E, P_Z, P_N = 931, 939, 892

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write() -> None:
    (pathlib.Path(__file__).resolve().parent / "probe_330_humid.txt").write_text(
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


def main() -> int:
    import app as m

    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 600.0

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    P_HEATFAULT = 924      # HeatingFaultDisp
    P_HUMVALVE = 169       # HumidtyValve（加湿阀）
    regs = [P_T, P_KPS, P_TIS, P_KDS, P_SDF, P_SET, P_SENS, P_SYSSTEP,
            P_E, P_Z, P_N, P_HEATFAULT, P_HUMVALVE]

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
    t_, kps, tis, kds = v[P_T], v[P_KPS], v[P_TIS], v[P_KDS]
    sdf = v[P_SDF]
    say("=== 330 加湿 PID 动态记录（规格书 3.8 验算，纯 Modbus）===")
    say("参数: KPS=%d  TIS=%ds  KDS=%d  T=%ds  SDF=%.1f%%RH"
        % (kps, tis, kds, t_, sdf / 10.0))
    say()
    say("   t | Sys | 设定 实际 | E(931) | N(892) BX Z(939) 期望Z | 备注")
    # 定时注入：改【湿度设定值】[162] 造偏差，把 N 推着穿过 BX 各档
    #   (触发秒, 寄存器, 值, 标签)
    # 注入计划留空 —— 由用户在 HMI 上手动改【湿度设定值】，探针只记录不写入。
    sched: list[tuple[float, int, int, str]] = []
    sched_left = list(sched)
    prev = None
    prev_n = None
    prev_e = None
    e1 = e2 = None
    t0 = time.time()
    while time.time() - t0 < seconds:
        el = time.time() - t0
        for item in list(sched_left):
            if el >= item[0]:
                sched_left.remove(item)
                try:
                    client.write_single_register(SLAVE, item[1], item[2] & 0xFFFF)
                    say(f"  [{el:6.0f}] >>> 注入 [{item[1]}] = {item[2]}   {item[3]}")
                except Exception as exc:  # noqa: BLE001
                    say(f"  [{el:6.0f}] !! 注入失败: {exc}")
        v = rd_many(regs)
        E, Z, N = v[P_E], v[P_Z], v[P_N]
        sysstep, setp, sens = v[P_SYSSTEP], v[P_SET], v[P_SENS]

        # PC 侧按规格书公式重算（用固件那套整数 + 向零截断）
        if e1 is None:
            e1 = E
            e2 = E
        num = (E - e1) * tis * t_ + t_ * t_ * E + kds * tis * (E - 2 * e1 + e2)
        den = 10 * tis * t_ if tis * t_ else 1
        bx = bx10_of(N)
        raw = kps * bx * num * 1000 // den if den > 0 else 0
        # C 的向零截断
        scaled = abs(raw) // 1000
        scaled = scaled if raw >= 0 else -scaled
        note = ""
        if abs(E) * 4 < sdf:
            note = "死区"
            scaled = 0
        elif not num:
            note = ""

        hf = v[P_HEATFAULT]
        key = (sysstep, setp, sens, E, Z, N, hf)
        if key != prev:
            say("  %5.0f | %2d | %5.1f %5.1f | %6d | %4d %3d %5d %6d | 制热故障=%d | %s"
                % (el, sysstep, setp / 10.0, sens / 10.0, E, N, bx, Z, scaled, hf, note))
            prev = key
        e2, e1 = e1, E
        time.sleep(1.0)

    say()
    say("结束")
    client.close()
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
