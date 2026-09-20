"""通用 330 寄存器读/写（Modbus RTU, COM6, slave 1）—— 地址就是 Parameter 下标（0 基址）。

用来做「注入类」操作，不碰 ST-Link，可和外机探针同时跑。

跑法：
    python.exe tools/rw330.py 2712                 # 读一个
    python.exe tools/rw330.py 2712 2715 2680       # 读多个（各读 1 个）
    python.exe tools/rw330.py 2712..2723           # 读一段
    python.exe tools/rw330.py 2712=100             # 写
    python.exe tools/rw330.py 2712=100 2713=0      # 写多个
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT = "COM6"
SLAVE = 1


def main() -> int:
    import app as m

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

    args = sys.argv[1:]
    if not args:
        print(__doc__)
        client.close()
        return 0

    # ---- 写 ----
    wrote = False
    for a in args:
        if "=" not in a:
            continue
        k, v = a.split("=", 1)
        addr, val = int(k, 0), int(v, 0)
        try:
            client.write_single_register(SLAVE, addr, val & 0xFFFF)
        except Exception as exc:  # noqa: BLE001
            print("  !! 写 [%d]=%d 异常: %s" % (addr, val, exc))
            continue
        time.sleep(0.3)
        back = s16(rd(addr)[0])
        print("  写 [%d] = %d  -> 回读 %d   %s"
              % (addr, val, back, "OK" if back == val else "!! 不一致"))
        wrote = True

    # ---- 读 ----
    for a in args:
        if "=" in a:
            continue
        if ".." in a:
            lo, hi = (int(x, 0) for x in a.split(".."))
            print("--- [%d..%d] ---" % (lo, hi))
            for i in range(lo, hi + 1):
                print("  [%5d] = %6d" % (i, s16(rd(i)[0])))
        else:
            addr = int(a, 0)
            print("  [%5d] = %6d" % (addr, s16(rd(addr)[0])))

    if not wrote and not any("=" not in a for a in args):
        pass
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
