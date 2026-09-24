"""直读 330 的压缩机启动状态机 RAM —— 定位"目标 4 实际 3"到底卡在哪道门。

**只用 ST-Link，不碰串口、不写任何寄存器。**

背景（见 `调试记录_20260916.md` §55.1 / A1-补2）：
330 加压缩机的路是 `CompAction.c:1136` 的循环 → `CompCanLoad()` 过 11 道门。
其中 4 道在 Modbus 上读不到，只能直读 RAM：
  #5 `CompStartReady()`   → CompStartGapCount
  #6 RetryInhibit         → 30 秒间隔到了没
  #7 UnitWriteStatus      → 330 不能已在下发
  #9 CompMinStopCount     → 最短停机 180 秒到了没
再加一个 `CompTargetLockedMask`：若 bit2(2#压机1) 为 0，说明**压根没选它**。

地址来源：`Project/Obj/PSC330RK-V10.axf` 的符号表（V10.15，2026-09-23 构建）。
⚠ **重新编译过就要重解**（脚本末尾附了解析函数）。

跑法（**必须先关掉占用板子的调试会话**）：
    C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe ^
        "D:\\Companty\\WEll thinker\\F\\code\\tools\\probe_330_comp_start_state.py"

⚠ pyocd **必须 attach 不能 halt** —— halt 会把板子冻死，"稳定数据"是假的。
"""

from __future__ import annotations

import struct
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---- 符号地址（V10.15，2026-09-23 构建）----------------------------------
ADDR = {
    "CompStartRetryInhibit": 0x200027F8,   # uint32[8]，用 CompStartIndex=(m-1)*2+c
    "CompStartPending": 0x20000F95,        # uint8
    "CompStartPendingModule": 0x20000F96,  # uint8
    "CompStartPendingComp": 0x20000F97,    # uint8
    "CompStartFeedbackCount": 0x20000F98,  # uint32
    "CompStartGapCount": 0x20000F9C,       # uint32
    "CompTargetLockedMask": 0x20000FA8,    # uint16
    # 下面两个数组：压机 (m,c) 用下标 2*m+c，所以基址要 +8 才是 1#压机1
    "CompMinStopCount_base2": 0x200026E8,  # uint32[10]（从 1#压机1 起）
    "CompMinRunCount_base2": 0x200025D0,   # uint32[10]
    "UnitWriteStatus": 0x20007858,         # 结构体数组，布局未定，只 dump 头 64 字节
    "Parameter": 0x200030C8,               # int16[]，用来看 [119]/[880]/[881]
}

COMP_NAMES = ["1#压机1", "1#压机2", "2#压机1", "2#压机2",
              "3#压机1", "3#压机2", "4#压机1", "4#压机2"]

COMP_STATUS = {0: "停止", 1: "故障", 2: "制冷", 3: "制热", 4: "除霜", 5: "禁用"}


def main() -> int:
    try:
        from pyocd.core.helpers import ConnectHelper
    except ImportError:
        print("!! 没装 pyocd")
        return 2

    session = ConnectHelper.session_with_chosen_probe(
        target_override="cortex_m",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        print("!! 没找到 ST-Link")
        return 1

    session.open()
    tgt = session.target
    if tgt.get_state() == tgt.State.HALTED:
        print("!! 进入时 HALTED —— 已 resume（不 halt 是硬要求）")
        tgt.resume()

    def u8(a: int) -> int:
        return tgt.read_memory_block8(a, 1)[0]

    def u16(a: int) -> int:
        return struct.unpack("<H", bytes(tgt.read_memory_block8(a, 2)))[0]

    def u32(a: int) -> int:
        return struct.unpack("<I", bytes(tgt.read_memory_block8(a, 4)))[0]

    def i16(a: int) -> int:
        return struct.unpack("<h", bytes(tgt.read_memory_block8(a, 2)))[0]

    def dump_u32(base: int, n: int) -> list[int]:
        return [u32(base + 4 * i) for i in range(n)]

    try:
        print("=" * 72)
        print("330 压缩机启动状态机 RAM 快照")
        print("=" * 72)

        p = ADDR["Parameter"]
        print()
        print("【330 寄存器视角】")
        for name, idx in (("CompNumSet 目标台数", 118),
                          ("CompNumCur 330认为在跑的台数", 119),
                          ("IndoorPidNDisp 需求N(千分制)", 880),
                          ("IndoorTargetCompDisp 目标台数", 881),
                          ("SystemNengry 加减载命令", 707),
                          ("SysStep", 709)):
            print(f"  [{idx:>4}] {name:<28} = {i16(p + 2 * idx)}")

        mask = u16(ADDR["CompTargetLockedMask"])
        print()
        print("【目标锁定掩码】")
        print(f"  CompTargetLockedMask = {mask:#06x}   置位 bit {[i for i in range(16) if mask & (1 << i)]}")
        print(f"    bit0~3 = 1#压机1/1#压机2/2#压机1/2#压机2")
        if mask & 0x0F != 0x0F:
            print("    ⚠ bit0~3 不全是 1 —— **有可能压根没选 2#压机1**（与「卡在5/7/9」同形）")
        else:
            print("    ✓ bit0~3 全 1 —— 4 台都被选中，那就会轮到 2#压机1")

        retry = dump_u32(ADDR["CompStartRetryInhibit"], 8)
        stopc = dump_u32(ADDR["CompMinStopCount_base2"], 8)
        runc = dump_u32(ADDR["CompMinRunCount_base2"], 8)

        print()
        print("【逐台状态】")
        print(f"  {'压机':<10}{'RetryInhibit':>14}{'MinStopCount':>15}{'MinRunCount':>14}   CompStatus")
        for i, nm in enumerate(COMP_NAMES):
            st = i16(p + 2 * (1550 + (i // 2) * 70 + 5 + (i % 2)))
            print(f"  {nm:<10}{retry[i]:>14}{stopc[i]:>15}{runc[i]:>14}   "
                  f"{st} ({COMP_STATUS.get(st, '?')})")

        print()
        print("【启动时序】")
        gap = u32(ADDR["CompStartGapCount"])
        pend = u8(ADDR["CompStartPending"])
        pmod = u8(ADDR["CompStartPendingModule"])
        pcmp = u8(ADDR["CompStartPendingComp"])
        fb = u32(ADDR["CompStartFeedbackCount"])
        print(f"  CompStartGapCount      = {gap:>6}   （要 ≥300 才允许起下一台，即 30 秒间隔）")
        print(f"  CompStartPending       = {pend:>6}")
        if pend:
            idx = (pmod - 1) * 2 + pcmp if pmod >= 1 else -1
            who = COMP_NAMES[idx] if 0 <= idx < 8 else "?"
            print(f"    → 正在等 {who} 的反馈（Module={pmod} Comp={pcmp}）")
            print(f"      CompStartFeedbackCount = {fb} / 60   （到 60 就判失败、抑制 300 秒）")
        else:
            print("    → 当前没有在等的启动请求")

        print()
        print("【判读】")
        r2, s2 = retry[2], stopc[2]
        if r2 != 0:
            print(f"  ★ RetryInhibit[2#压机1] = {r2} ≠ 0")
            print("    ⇒ **启动失败被抑制**：330 试过、316 没在 60 秒内反馈。")
            print(f"    ⇒ 还有约 {r2} 秒放开。放开后的 60 秒窗口里把 ST-Link 换到 2# 的 316 板，")
            print("       看它收没收到启动命令、卡在哪个条件。")
        elif s2 < 180:
            print(f"  ★ MinStopCount[2#压机1] = {s2} < 180")
            print("    ⇒ **卡最短停机时间**：这一路刚「停」过，`CompStatus` 一定在 0↔2 之间抖过。")
            print("    ⇒ 查 316 那边为什么起一下就停。")
        elif mask & 0x04 == 0:
            print("  ★ TargetLockedMask 的 bit2 = 0")
            print("    ⇒ **2#压机1 压根不在目标掩码里** —— 330 不会请求它。")
            print("    ⇒ 往 CompTargetSelection* 的目标选择逻辑查。")
        else:
            print("  ★ 三个值都正常 ⇒ 卡在 #5(#CompStartReady) / #7(UnitWriteStatus) / #10(EnviOFFfalg)")
            print(f"     CompStartGapCount={gap}（<300 就是还没到间隔）")

        print()
        print("【UnitWriteStatus 头 64 字节（布局未定，供比对）】")
        raw = bytes(tgt.read_memory_block8(ADDR["UnitWriteStatus"], 64))
        for off in range(0, 64, 16):
            print(f"  +{off:02d}: " + " ".join(f"{b:02x}" for b in raw[off:off + 16]))

    finally:
        if tgt.get_state() == tgt.State.HALTED:
            print("\n!! 结束前处于 HALTED —— resume")
            tgt.resume()
        session.close()

    print()
    print("采样时刻:", time.strftime("%Y-%m-%d %H:%M:%S"))
    return 0


# ---- 重新解析符号（重新编译后跑一次，把结果填回上面 ADDR）------------------
def resolve_symbols(axf_path: str, names: list[str]) -> dict[str, int]:
    import struct as _s
    d = open(axf_path, "rb").read()
    e_shoff = _s.unpack("<I", d[0x20:0x24])[0]
    e_shentsize = _s.unpack("<H", d[0x2E:0x30])[0]
    e_shnum = _s.unpack("<H", d[0x30:0x32])[0]
    e_shstrndx = _s.unpack("<H", d[0x32:0x34])[0]
    secs = []
    for i in range(e_shnum):
        o = e_shoff + i * e_shentsize
        n, t, fl, ad, off, sz, lk, inf, al, es = _s.unpack("<10I", d[o:o + 40])
        secs.append(dict(typ=t, off=off, size=sz, link=lk))
    st = secs[e_shstrndx]
    out = {}
    for sec in secs:
        if sec["typ"] == 2:
            strtab = secs[sec["link"]]
            for i in range(sec["size"] // 16):
                o = sec["off"] + i * 16
                nm, val, sz, inf, oth, sh = _s.unpack("<IIIBBH", d[o:o + 16])
                q = d[strtab["off"] + nm:]
                q = q[:q.index(b"\x00")].decode("latin1")
                if q in names:
                    out[q] = val
    return out


if __name__ == "__main__":
    sys.exit(main())
