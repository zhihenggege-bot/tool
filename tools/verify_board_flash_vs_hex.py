# -*- coding: utf-8 -*-
"""把板上 flash 和本地 .hex 逐字节比 —— 判断烧进去的到底是哪一版。

背景：V10.8（§26.4 那次失败的修法）**没有拨版本号**，
`_fix_scr_pulse.py` 的 EDITS 只有 A/B/C 三处代码改动，没有动 User.h 的
PSC330_VERSION_MINOR/DAY。所以板上报的 [2622..2627] 仍是 330/10/7/2026/9/20，
**V10.7 和 V10.8 从版本号上分不出来**。只能比 flash。

用法：
    python.exe tools/verify_board_flash_vs_hex.py
只读，attach 模式（不停核）。
"""
from __future__ import annotations

import pathlib
import sys

from pyocd.core.helpers import ConnectHelper

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEX = ROOT / "PSC330RK-V10-内机/Project/Obj/PSC330RK-V10.hex"
OUT = pathlib.Path(__file__).resolve().parent / "_flash_cmp.txt"

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def parse_hex(path: pathlib.Path) -> dict[int, int]:
    """Intel HEX -> {绝对地址: 字节}。"""
    mem: dict[int, int] = {}
    base = 0
    for line in path.read_text(encoding="ascii").splitlines():
        line = line.strip()
        if not line.startswith(":"):
            continue
        raw = bytes.fromhex(line[1:])
        n, addr, rectype = raw[0], (raw[1] << 8) | raw[2], raw[3]
        data = raw[4:4 + n]
        if rectype == 0x00:
            for i, b in enumerate(data):
                mem[base + addr + i] = b
        elif rectype == 0x04:
            base = ((data[0] << 8) | data[1]) << 16
        elif rectype == 0x02:
            base = ((data[0] << 8) | data[1]) << 4
    return mem


def blocks_of(mem: dict[int, int]) -> list[tuple[int, int]]:
    """把地址集合收成连续区间 [(start, end_exclusive)]。"""
    adds = sorted(mem)
    out: list[tuple[int, int]] = []
    s = p = adds[0]
    for a in adds[1:]:
        if a == p + 1:
            p = a
            continue
        out.append((s, p + 1))
        s = p = a
    out.append((s, p + 1))
    return out


def main() -> int:
    if not HEX.exists():
        say("✗ 找不到 %s" % HEX)
        return 1

    mem = parse_hex(HEX)
    blocks = blocks_of(mem)
    total = len(mem)
    say("本地 hex : %s" % HEX.name)
    say("           字节 %d，连续区段 %d 个，地址 0x%08X ~ 0x%08X"
        % (total, len(blocks), min(mem), max(mem)))
    say()

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f407ze",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        say("✗ 连不上 ST-Link")
        return 1

    bad_total = 0
    bad_blocks: list[str] = []
    with session:
        tgt = session.target
        say("连接成功。内核状态 = %s" % tgt.get_state())

        for (s, e) in blocks:
            want = bytes(mem[a] for a in range(s, e))
            off = 0
            while off < len(want):
                chunk = min(4096, len(want) - off)
                got = bytes(tgt.read_memory_block8(s + off, chunk))
                if got != want[off:off + chunk]:
                    for i in range(chunk):
                        if got[i] != want[off + i]:
                            a = s + off + i
                            bad_total += 1
                            if len(bad_blocks) < 40:
                                bad_blocks.append(
                                    "  0x%08X  hex=%02X  板=%02X" % (a, want[off + i], got[i]))
                off += chunk

        st = tgt.get_state()
        say()
        say("读完。内核状态 = %s" % st)
        if st == tgt.State.HALTED:
            say("!! 核是 HALTED，正在 resume")
            tgt.resume()
            say("   resume 后 = %s" % tgt.get_state())

    say()
    if bad_total == 0:
        say("★ 判决：板上 flash 与本地 %s **逐字节完全一致**。" % HEX.name)
        say("   ⇒ 板子跑的就是本地这一版（V10.7），**不是 V10.8**。")
    else:
        say("★ 判决：**不一致**，共 %d 字节不同（前 40 个）：" % bad_total)
        for l in bad_blocks:
            say(l)
        say()
        say("   ⇒ 板上不是本地这一版 V10.7。"
            "很可能仍是 V10.8（§26.4 那版）⇒ 重烧后再做判断。")

    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
