"""写 330 网关的「外机参数」（21 个里任选），用于把化霜等参数调到测试值。

协议照抄工具 app.py 的 write_outdoor_gateway_register()：
  1. 等网关写槽空闲（330[base+43] != 1）
  2. FC06 单寄存器写（多寄存器会被 330 的 modbus.c 丢帧）
  3. **判据只看镜像回读 == 目标值**（状态位比镜像早约 5.5 秒，会读到上一轮的遗留值）
  → 一次写约 12~18 秒

范围校验：固件侧 ErrorCheck.c 会用 Parameter_min/max 卡（写超范围会被拒/钳），
本脚本先在 330 侧按 OUTDOOR_GATEWAY_MIN/MAX 预检，避免白等一次。

跑法：
    python.exe tools/set_316_gateway_param.py --unit 2 --list
    python.exe tools/set_316_gateway_param.py --unit 2 --set 17=150 18=20 19=2
    python.exe tools/set_316_gateway_param.py --unit 2 --defrost-test      # 化霜测试预设值
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT = "COM6"
SLAVE = 1
GW_BASE = 1830
GW_DIAG = 42

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def write_out() -> None:
    (pathlib.Path(__file__).resolve().parent / "set_316_gateway_param.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


# 化霜测试预设：能缩短的都用范围下限；17 取上限（最易满足）
DEFROST_TEST = {
    17: 150,   # 环境温度定时化霜温度设定值 15.0C（范围 5.0~15.0，取上限）
    18: 20,    # 环境温度定时化霜时间间隔 20min（下限）
    19: 2,     # 环境温度定时化霜时间 2min（下限）
    20: 5,     # 化霜开始前压缩运转最小时间 5min（下限）
    25: 300,   # 化霜结束室外机翅片温度 30.0C（下限，本来就是这个值）
    26: 2,     # 环温>0 化霜时间 2min（下限）
    27: 2,     # 环温<0 化霜时间 2min（下限）
}


def main() -> int:
    import app as m

    def opt(name, default=None):
        if name not in sys.argv:
            return default
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default

    unit = int(opt("--unit", 2))

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

    gw = GW_BASE + (unit - 1) * m.OUTDOOR_GATEWAY_STEP

    def rd_param(off):
        return s16(rd(gw + off)[0])

    def dump():
        say(f"--- 外机{unit} 网关参数（0~20 可写；17~27 是化霜段）---")
        for off in range(len(m.OUTDOOR_GATEWAY_RW_NAMES)):
            if off in (28, 29, 30, 31):    # 地址设定段，别乱动
                continue
            lo, hi = m.OUTDOOR_GATEWAY_MIN[off], m.OUTDOOR_GATEWAY_MAX[off]
            nm = m.OUTDOOR_GATEWAY_RW_NAMES[off]
            say("  [%2d] %-30s = %6d   (范围 %d~%d)" % (off, nm, rd_param(off), lo, hi))

    if "--list" in sys.argv:
        dump()
        client.close()
        write_out()
        return 0

    pairs: dict[int, int] = {}
    if "--defrost-test" in sys.argv:
        pairs.update(DEFROST_TEST)
    for a in sys.argv:
        if "=" in a and not a.startswith("--"):
            k, v = a.split("=", 1)
            try:
                pairs[int(k)] = int(v)
            except ValueError:
                say(f"!! 参数格式不对: {a}（要 偏移=值，例如 17=150）")
                client.close()
                write_out()
                return 2

    if not pairs:
        say(__doc__.split("跑法：")[1].strip())
        client.close()
        write_out()
        return 2

    say(f"=== 写外机{unit} 网关参数 ===")
    for off in sorted(pairs):
        tgt = pairs[off]
        lo, hi = m.OUTDOOR_GATEWAY_MIN[off], m.OUTDOOR_GATEWAY_MAX[off]
        nm = m.OUTDOOR_GATEWAY_RW_NAMES[off]
        if not lo <= tgt <= hi:
            say(f"  !! [{off}] {nm}: {tgt} 超出范围 {lo}~{hi}，跳过")
            continue
        cur = rd_param(off)
        if cur == tgt:
            say(f"  [{off}] {nm}: 已是 {tgt}，跳过")
            continue
        # 等写槽空闲
        deadline = time.time() + 30
        while time.time() < deadline:
            if s16(rd(gw + GW_DIAG + 1)[0]) != 1:
                break
            time.sleep(0.35)
        say(f"  [{off}] {nm}: {cur} -> {tgt} ...")
        t0 = time.time()
        try:
            client.write_single_register(SLAVE, gw + off, tgt & 0xFFFF)
        except Exception as exc:  # noqa: BLE001
            say(f"    !! 写异常: {exc}")
            continue
        time.sleep(0.08)
        ok = False
        while time.time() - t0 < 45:
            time.sleep(0.5)
            if rd_param(off) == tgt:
                ok = True
                break
        say(f"    {'OK' if ok else '!! 超时'}  {time.time() - t0:.1f}s  "
            f"回读={rd_param(off)}")

    say()
    dump()
    client.close()
    write_out()
    return 0


if __name__ == "__main__":
    sys.exit(main())
