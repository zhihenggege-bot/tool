"""纯 Modbus 写 316 的 NTC 偏移 —— **不碰 ST-Link**，可以和外机探针同时跑。

链路（2026-09-17 逐环核对）：
    NTC[i] = round(Tempbuf*10) + Parameter[493-i]     （NTC16bit.c:171）
    镜像是错开 6 的，于是 NTC[i] 的偏移 == 330[2534 + (u-1)*16 + i]   （i = 0..7）

    显示值 = 真实值 + 偏移     ⇒     偏移 = 目标显示值 − 真实值

只要知道**真实值**，就不用 ST-Link 读显示值，直接算偏移写下去。
真实值 = 上次读到的显示值 − 上次的偏移（温度漂移很慢，够用）。

跑法：
    python.exe tools/set_ntc_offset.py --unit 1 --show
    python.exe tools/set_ntc_offset.py --unit 1 --disp 5=3.0 --real 5=8.4
    python.exe tools/set_ntc_offset.py --unit 1 --raw 5=-54        # 直接写偏移
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
COMPACT_NUM = 16
GW_BASE = 1830
GW_DIAG = 42

NTC_NAME = {0: "环温 NTC1", 1: "翅片1 NTC2", 2: "翅片2 NTC3", 3: "排气 NTC4",
            4: "排气 NTC5", 5: "吸气1 NTC6", 6: "吸气2 NTC7", 7: "(未用)"}


def main() -> int:
    import app as m

    def opt(name, default=None):
        if name not in sys.argv:
            return default
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default

    unit = int(opt("--unit", 1))
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

    comp = COMPACT_BASE + (unit - 1) * COMPACT_NUM
    gw = GW_BASE + (unit - 1) * m.OUTDOOR_GATEWAY_STEP

    def dump():
        print("--- 外机%d NTC 偏移（330[%d..%d]）---" % (unit, comp, comp + 7))
        for i in range(8):
            print("  NTC[%d] %-10s 偏移 %5d (%+.1fC)"
                  % (i, NTC_NAME[i], s16(rd(comp + i)[0]), s16(rd(comp + i)[0]) / 10.0))

    dump()

    # 收集写入请求：按最后一个 `--xxx` 开关决定后续 `k=v` 的归属
    disp: dict[int, float] = {}
    real: dict[int, float] = {}
    raw: dict[int, int] = {}
    mode = None
    for a in sys.argv[1:]:
        if a.startswith("--"):
            mode = a[2:]
            continue
        if "=" not in a:
            continue
        k, v = a.split("=", 1)
        try:
            if mode == "disp":
                disp[int(k)] = float(v)
            elif mode == "real":
                real[int(k)] = float(v)
            elif mode == "raw":
                raw[int(k)] = int(v)
            else:
                print("  !! 没有前置开关，忽略:", a)
        except ValueError:
            print("  !! 参数格式不对:", a)

    if not disp and not raw:
        client.close()
        return 0

    for i in sorted(set(disp) | set(raw)):
        if i not in NTC_NAME:
            print("  !! NTC[%d] 超出 0~7，跳过" % i)
            continue
        if i in raw:
            new_off = raw[i]
        else:
            if i not in real:
                print("  !! NTC[%d] 给了 --disp 但没给 --real，跳过" % i)
                continue
            new_off = int(round(disp[i] * 10)) - int(round(real[i] * 10))
        if i in real:
            shown = (int(round(real[i] * 10)) + new_off) / 10.0
            print("  NTC[%d] %-10s 真实 %.1fC -> 偏移 %d  (显示应为 %.1fC)"
                  % (i, NTC_NAME[i], real[i], new_off, shown))
        else:
            print("  NTC[%d] %-10s -> 偏移 %d" % (i, NTC_NAME[i], new_off))
        deadline = time.time() + 30
        while time.time() < deadline:
            if s16(rd(gw + GW_DIAG + 1)[0]) != 1:
                break
            time.sleep(0.35)
        t0 = time.time()
        try:
            client.write_single_register(SLAVE, comp + i, new_off & 0xFFFF)
        except Exception as exc:  # noqa: BLE001
            print("    !! 写异常:", exc)
            continue
        time.sleep(0.08)
        ok = False
        while time.time() - t0 < 45:
            time.sleep(0.5)
            if s16(rd(comp + i)[0]) == new_off:
                ok = True
                break
        print("    %s  %.1fs" % ("OK" if ok else "!! 超时", time.time() - t0))

    print()
    dump()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
