# -*- coding: utf-8 -*-
"""用**板上真实配置**回放监控工具的 `_validate_mode_config`，验证补丁是否解除了误拦。

只读板子（Modbus），不写；不启动 GUI（直接 import app 模块调静态方法）。

判定：
  A. 当前实配（含 [332]=4 + [333]=4 双可控硅）→ 改前必被拦，改后必须放行
  B. 用户要写的 [129]=0→1            → 必须放行（这就是被挡下的那次操作）
  C. [128]=5 + [332]=4 + [129]=0     → 必须拦（备注4，改前漏放）
  D. [128]=3 + [332]=2 + [129]=0     → 必须拦（备注4 原有行为不能丢）

输出写 UTF-8 文件（控制台是 GBK，直接 print 中文会乱码）。
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))
sys.path.insert(0, str(ROOT / "psc330_monitor_tool"))

NEEDED = [127, 128, 129, 329, 330, 332, 333, 335, 336, 337, 338,
          340, 341, 342, 356, 357, 377, 381, 383, 384, 450, 451]

lines: list[str] = []


def say(s: str = "") -> None:
    lines.append(s)


def read_board() -> dict[int, int]:
    import app as m
    client = m.ModbusRtuClient()
    client.open("COM6", m.DEFAULT_BAUD)
    out: dict[int, int] = {}
    try:
        for a in NEEDED:
            for _ in range(4):
                try:
                    v = client.read_holding_registers(1, a, 1)[0] & 0xFFFF
                    out[a] = v - 0x10000 if v & 0x8000 else v
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.2)
    finally:
        client.close()
    return out


def check(app_mod, raw: dict[int, int]) -> str:
    try:
        app_mod.Psc330MonitorApp._validate_mode_config(dict(raw))
        return "放行"
    except ValueError as exc:
        return "拦截: %s" % exc


def main() -> int:
    import app as m

    raw = read_board()
    say("板上实配（只读）：")
    for a in NEEDED:
        say("  [%3d] = %d" % (a, raw.get(a, -1)))
    say()

    cases = [
        ("A 当前实配原样", {}),
        ("B 用户要写的 [129]=1", {129: 1}),
        ("C [128]=5 + [332]=4 + [129]=0（备注4，应拦）",
         {128: 5, 332: 4, 129: 0, 127: 1}),
        ("D [128]=3 + [332]=2 + [129]=0（备注4，应拦）",
         {128: 3, 332: 2, 129: 0, 127: 1}),
        ("E [128]=4 + [332]=3 + [129]=0（备注4，应拦）",
         {128: 4, 332: 3, 129: 0, 127: 1}),
        ("F [128]=2 + [332]=4 + [129]=0（当前那类，应放行）",
         {128: 2, 332: 4, 129: 0, 127: 1}),
    ]

    expect = {"A": "放行", "B": "放行", "C": "拦截", "D": "拦截", "E": "拦截", "F": "放行"}
    bad = 0
    say("回放结果：")
    say("  %-2s %-46s %-9s %s" % ("#", "场景", "预期", "实际"))
    for label, mut in cases:
        r = dict(raw)
        r.update(mut)
        got = check(m, r)
        verdict = got.split(":")[0]
        ok = "OK " if verdict == expect[label[0]] else "!! "
        if not ok.strip():
            bad += 1
        say("  %s %-46s %-9s %s" % (ok, label, expect[label[0]], got))
    say()
    say("结论：%s" % ("全部符合预期 ✅" if bad == 0 else "有 %d 条不符 ❌" % bad))

    pathlib.Path(__file__).with_suffix(".txt").write_text("\n".join(lines) + "\n",
                                                          encoding="utf-8")
    print("done, see verify_monitor_scr_validation.txt")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
