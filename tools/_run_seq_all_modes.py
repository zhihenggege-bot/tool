# -*- coding: utf-8 -*-
"""依次把 §3.3 剩下的模式跑一遍：制冷 → 通风 → 消毒。

每轮：切模式 → **放开串口**（关键！本进程和子进程同抢 COM6 会把读值搞乱，实测踩过）
      → 跑 probe_330_startup_seq.py → 收结果 → 复原 → 下一轮。

⚠ 消排毒那三个模式（[236]∈{3,4,5}）**根本不调 SysBoardAction**（UserAction.c:3382-3388
  在消排毒分支直接 return），所以 SysStep 永远到不了 2 ⇒ 不能给 `--cycle`
  （会死等运行态）。改用**被动录制**，由"切模式"本身当触发。

跑法： python.exe tools/_run_seq_all_modes.py
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1
HERE = pathlib.Path(__file__).resolve().parent
PROBE = HERE / "probe_330_startup_seq.py"
OUTTXT = HERE / "probe_330_startup_seq.txt"

# (名字, 要写的寄存器, 探针参数, 探针秒数)
PLAN = [
    ("排毒", {236: 4, 324: 3}, [], 700),                    # 被动录制
    ("消排毒", {236: 5, 323: 3, 324: 3}, [], 1500),          # 消毒段+30s+排毒段，最长的一条
]
SAVE = [236, 323, 324, 325, 326]

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode("gbk", "replace").decode("gbk", "replace"), flush=True)


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def main() -> int:
    import app as m

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    def rd(a):
        for _ in range(3):
            try:
                return s16(client.read_holding_registers(SLAVE, a, 1)[0])
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        return None

    def wr(a, v):
        for _ in range(3):
            try:
                client.write_single_register(SLAVE, a, v & 0xFFFF)
                time.sleep(0.3)
                return rd(a) == v
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        return False

    orig = {a: rd(a) for a in SAVE}
    say("=== §3.3 剩余模式逐轮实测 ===")
    say("原值： %s" % ", ".join("[%d]=%s" % (a, orig[a]) for a in SAVE))
    say()

    for name, sets, args, secs in PLAN:
        say("############ %s ############" % name)
        for a, v in sets.items():
            say("  写 [%d] = %d  %s" % (a, v, "OK" if wr(a, v) else "!! 失败"))
        time.sleep(3)
        say("  切换后：[236]=%s [323]=%s [709]=%s [885]=%s"
            % (rd(236), rd(323), rd(709), rd(885)))

        client.close()                     # ← 必须放串口，否则子进程读值错乱
        say("  跑探针 %d 秒 %s …" % (secs, " ".join(args)))
        try:
            subprocess.run([sys.executable, str(PROBE), str(secs)] + args,
                           capture_output=True, timeout=secs + 300)
        except subprocess.TimeoutExpired:
            say("  !! 探针超时")
        dst = HERE / ("_seq_%s.txt" % name)
        if OUTTXT.exists():
            shutil.copy(OUTTXT, dst)
            say("  结果 → %s" % dst.name)
        client = m.ModbusRtuClient()
        client.open(PORT, m.DEFAULT_BAUD)
        say()

    say("--- 复原 ---")
    for a, v in orig.items():
        if v is not None:
            wr(a, v)
    say("  已写回： %s" % ", ".join("[%d]=%s" % (a, orig[a]) for a in SAVE))
    say("  复原后实测：[236]=%s [709]=%s" % (rd(236), rd(709)))
    client.close()
    (HERE / "_run_seq_all_modes.txt").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
