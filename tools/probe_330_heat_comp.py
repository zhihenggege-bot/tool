# -*- coding: utf-8 -*-
"""切到「热泵制热」并跑 §3.4.2 压缩机 PID 对账（Z(KR) 公式）。

规格书 §3.4.2 热泵制热那条与制冷的差别：
    N(KR)=MIN(1,N(KR-1)+Z(KR))
    Z(KR)=KPR*BX/100*[E(KR)-E(KR-1)+T/TIR*E(KR)+KDR/T*(E(KR)-2E(KR-1)+E(KR-2))]
    E(KR) = WD − 室内温度        （制冷是 室内温度 − WD，**符号相反**）
    死区 -WDF/4 < E < WDF/4 ⇒ Z=0  （**没有 YS 项**）
    台数：Z>0 → ROUNDUP(CN*N)；Z<0 → INT(CN*N)；Z=0 保持   （**没有"制冷有再热"的 MAX(1,·)**）

本脚本负责**切换工况 + 复原**，对账本体直接复用已验证的 `probe_330_outdoor_pid.py`
（它按 [236] 自动选制冷/制热分支；用子进程调，串口开闭由它自己管）。

⚠ 切到热泵制热会让固件**真给外机下压缩机启动指令**（用户 2026-09-20 已确认接受）。
⚠ 复原清单：脚本会把下面 5 个寄存器改回原值，并在结束时打印。
    [236] UserWorkModeSetTEMP  工作模式（1=制热）
    [128] HeatModeSet          制热方式（1=热泵制热）
    [127] ReheatEnableSet      再热/辅热启用（辅热要它=1）
    [129] HeatReheatShareSet   共用
    [332] ReheatModeSet        再热/辅热方式
    [416]~[418] / [426]~[428]  PID 增益（用 --kpl 提速时才动 [426]）

跑法：
    python.exe tools/probe_330_heat_comp.py 180            # 跑 180 秒
    python.exe tools/probe_330_heat_comp.py 300 --kpl 50   # 临时把 KPR 提到 50（N 跑得快）
    python.exe tools/probe_330_heat_comp.py --restore      # 只复原，不跑
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1
OUT = pathlib.Path(__file__).resolve().parent / "probe_330_heat_comp.txt"
PROBE = pathlib.Path(__file__).resolve().parent / "probe_330_outdoor_pid.py"
PY = sys.executable

# 切热泵制热要动的寄存器
SET = {236: 1, 128: 1, 127: 1}          # 制热 / 热泵制热 / 再热辅热启用
CFG = [236, 128, 127, 129, 332, 426, 427, 428, 416, 417, 418, 2678, 214, 709]
WM = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排风", 5: "自动"}

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

    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 180.0
    kpl = None
    for a in sys.argv[1:]:
        if a.startswith("--kpl="):
            kpl = int(a.split("=", 1)[1])
    restore_only = "--restore" in sys.argv

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

    orig = {a: rd(a) for a in CFG}
    say("=== 330 §3.4.2 热泵制热压缩机 PID 对账（驱动脚本）===")
    say("原值：")
    for a in CFG:
        say("  [%4d] = %s" % (a, orig[a]))
    say()
    say("【复原清单】结束时写回：")
    for a, v in orig.items():
        if v is not None:
            say("  [%4d] = %d" % (a, v))
    say()

    if restore_only:
        for a, v in orig.items():
            if v is not None:
                wr(a, v)
        say("已复原。")
        client.close()
        OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        return 0

    # ---- 切热泵制热 ----
    say("--- 切「热泵制热」---")
    for a, v in SET.items():
        ok = wr(a, v)
        say("  写 [%d] = %d  %s" % (a, v, "OK" if ok else "!! 回读不一致"))
    if kpl is not None:
        say("  写 [426] KPR = %d （提速用，结束复原 %s）%s"
            % (kpl, orig[426], "OK" if wr(426, kpl) else "!! 失败"))
    say()
    time.sleep(1.0)
    say("切换后：[236]=%s [128]=%s [127]=%d [129]=%d [332]=%d CN=%s [426]=%s"
        % (WM.get(rd(236), rd(236)), rd(128), rd(127), rd(129), rd(332), rd(2678), rd(426)))
    say()

    # ---- 跑对账本体（子进程，串口由它自己开关）----
    # ⚠ 必须先放掉串口！否则本进程和子进程抢同一个 COM6，读回来的值是错乱的
    #   （实测过：子进程把 [236] 读成 0，看起来像"模式被改回制冷了"，追了很久）。
    client.close()
    say("--- 调用 probe_330_outdoor_pid.py %.0f 秒 ---" % seconds)
    say()
    try:
        r = subprocess.run([PY, str(PROBE), str(seconds), "30"],
                           capture_output=True, timeout=seconds + 420)
        tail = (r.stdout or b"").decode("gbk", "replace").strip().splitlines()[-3:]
        for ln in tail:
            say("  | " + ln)
    except subprocess.TimeoutExpired:
        say("  !! 对账脚本超时")
    say()

    # ---- 复原 ----
    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)
    say("--- 复原 ---")
    for a, v in orig.items():
        if v is not None:
            wr(a, v)
    say("  已写回：%s" % ", ".join("[%d]=%d" % (a, v) for a, v in orig.items() if v is not None))
    say()
    say("  复原后实测：[236]=%s [128]=%s [127]=%s [426]=%s"
        % (rd(236), rd(128), rd(127), rd(426)))

    client.close()
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
