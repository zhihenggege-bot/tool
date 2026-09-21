# -*- coding: utf-8 -*-
"""验证 V10.9 修复：可控硅模式下 Y15/Y16 两个接触器是否稳定吸合。

读两个地方，互相印证：
  RAM : output[] 基址 0x20001364 —— Y15=+13(0x...71) Y16=+14  Y17=+15
  GPIO: GPIOG ODR 0x40021814     —— Y15=bit15  Y16=bit13  Y17=bit12
GPIO ODR 才是真正驱动继电器的电平。

⚠ 必须 attach（connect_mode="attach"）—— 默认 halt 会把板子冻死，见 pyocd-attach-not-halt。
⚠ 每次整块读 16 字节：分两次读单字节会采到 "01 00/00 01" 的假象（§26.2）。

跑法： python.exe tools/probe_330_scr_contactors.py 80
"""
from __future__ import annotations

import pathlib
import sys
import time

from pyocd.core.helpers import ConnectHelper

OUT = pathlib.Path(__file__).resolve().parent / "probe_330_scr_contactors.txt"

OUT_BASE = 0x20001364          # output[0..15]
GPIOG_ODR = 0x40021814
Y15_BIT, Y16_BIT, Y17_BIT = 15, 13, 12

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def main() -> int:
    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 80.0

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f407ze",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        say("✗ 连不上 ST-Link")
        return 1

    with session:
        tgt = session.target
        say("=== 330 可控硅模式接触器采样（V10.9 验证）===")
        say("连上时内核状态 = %s" % tgt.get_state())
        if tgt.get_state() == tgt.State.HALTED:
            say("!! 是 HALTED，立刻 resume")
            tgt.resume()
            say("   resume 后 = %s" % tgt.get_state())
        say("采样 %.0f 秒 …（每拍整块读 16 字节 output[]，另读 GPIOG ODR）" % seconds)
        say()

        ram_pattern: dict[str, int] = {}
        odr_pattern: dict[str, int] = {}
        samples = 0
        t0 = time.time()
        while time.time() - t0 < seconds:
            buf = bytes(tgt.read_memory_block8(OUT_BASE, 16))
            odr = int.from_bytes(bytes(tgt.read_memory_block8(GPIOG_ODR, 4)), "little")
            key = "%d%d%d" % (buf[13], buf[14], buf[15])
            ram_pattern[key] = ram_pattern.get(key, 0) + 1
            okey = "%d%d%d" % ((odr >> Y15_BIT) & 1, (odr >> Y16_BIT) & 1,
                               (odr >> Y17_BIT) & 1)
            odr_pattern[okey] = odr_pattern.get(okey, 0) + 1
            samples += 1
            time.sleep(0.05)

        st = tgt.get_state()
        say("采完 %d 次，内核状态 = %s" % (samples, st))
        if st == tgt.State.HALTED:
            say("!! HALTED，resume")
            tgt.resume()
            say("   resume 后 = %s" % tgt.get_state())

    say()
    say("RAM output[13][14][15] (Y15 Y16 Y17) 图案分布：")
    for k in sorted(ram_pattern, key=lambda x: -ram_pattern[x]):
        say("   %s  ×%-6d  %5.1f%%" % (k, ram_pattern[k], 100.0 * ram_pattern[k] / samples))
    say()
    say("GPIOG ODR bit15/13/12 (Y15 Y16 Y17) 图案分布：")
    for k in sorted(odr_pattern, key=lambda x: -odr_pattern[x]):
        say("   %s  ×%-6d  %5.1f%%" % (k, odr_pattern[k], 100.0 * odr_pattern[k] / samples))
    say()

    # 判据只看 GPIO ODR —— 那才是驱动继电器的电平。
    # RAM 上偶发的 000 是扫描内 "PreHeatControl 先清→Apply 再置" 的正常瞬态
    # （UserAction.c 里 3116 清、3144 置），而 WriteOutput() 在 User() **之前**跑，
    # 永远采不到那个窗口，所以它到不了引脚。别把这种瞬态判成"翻转"。
    top_odr, top_cnt = max(odr_pattern.items(), key=lambda kv: kv[1])
    n_y15 = sum(c for k, c in odr_pattern.items() if k[0] == "1")
    n_y16 = sum(c for k, c in odr_pattern.items() if k[1] == "1")
    say("GPIO ODR 上 Y15 为 1 的占比 %.2f%%，Y16 为 1 的占比 %.2f%%"
        % (100.0 * n_y15 / samples, 100.0 * n_y16 / samples))
    say("RAM 上非主图案的采样 %d 次（%.2f%%）—— 若都是瞬态 000，属正常"
        % (samples - ram_pattern.get(top_odr, 0), 100.0 * (samples - ram_pattern.get(top_odr, 0)) / samples))
    say()
    if top_cnt == samples and top_odr == "110":
        say("★ 判决：引脚全程恒为 Y15=1 Y16=1 Y17=0（region=2 该有的样子）"
            " —— **两个接触器稳定吸合，V10.9 修复生效**。")
    elif top_cnt == samples and top_odr == "000":
        say("★ 判决：引脚全程恒为 0 —— **接触器一动不动，修复没生效**。")
    elif top_cnt == samples:
        say("★ 判决：引脚全程恒为 %s —— 稳定，但与 region=2 的预期(110)不符，查判据。" % top_odr)
    else:
        say("★ 判决：**引脚在翻转**（见上分布）—— 仍有第二个写者，修复不完整。")

    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
