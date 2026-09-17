"""给 316 板做一次硬件复位，并对比复位前后的关键参数。

用途：验「AI 通道偏移（AiCfgOffset）能不能扛住复位」——
偏移在 Parameter[310]/[322]，如果复位后还在，说明它进了 EEPROM；
如果是 0，说明它只是 RAM，复位就没了（而 350 的迁移标记是 MAGIC，
不会再从 UserA0ValueSet 恢复）。

⚠ 用 pyocd 的 `reset()`（复位并运行），**不是** `reset_and_halt()`。
   复位后立刻查 state，万一落在 HALTED 就 resume 放开 —— 绝不能把板子留在停机态。

跑法：
    python.exe tools/reset_316.py            # 复位 + 前后对比
    python.exe tools/reset_316.py --dry-run  # 只看当前值，不复位
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))
import pt_tables as pt  # noqa: E402

PARAM_BASE = 0x2000164A
DRY = "--dry-run" in sys.argv

# 要在复位前后对比的量
WATCH16 = [
    ("AI0 偏移 (AI0 1#高压)", 310),
    ("AI1 偏移 (AI1 2#高压)", 322),
    ("A2/A3 偏移", 334),
    ("AI配置版本标记 [350]", 350),
    ("UserA0ValueSet [499]", 499),
    ("机型 [165]", 165),
    ("风机类型 [166]", 166),
    ("TL [172]", 172),
    ("TLD [173]", 173),
    ("制冷剂 [39]", 39),
    ("高压1 [1443]", 1443),
    ("高压2 [1445]", 1445),
    ("环温 [1422]", 1422),
]
WATCH8 = [
    ("OutdoorVfdOn", 0x20000D01),
    ("OutdoorFixedOn", 0x20000D02),
    ("OutdoorFanStage", 0x20000D00),
]
WATCH32 = [
    ("OutdoorVfdSpeed (0.1Hz)", 0x20000D30),
    ("OutdoorVfdForceFullCount", 0x20000D50),
]

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def read_all(tgt) -> str:
    def r8(a):
        return tgt.read_memory_block8(a, 1)[0]

    def r16(i):
        v = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        x = v[0] | (v[1] << 8)
        return x - 0x10000 if x & 0x8000 else x

    def r32(a):
        v = tgt.read_memory_block8(a, 4)
        return v[0] | (v[1] << 8) | (v[2] << 16) | (v[3] << 24)

    out = []
    for name, idx in WATCH16:
        out.append("    %-26s = %d" % (name, r16(idx)))
    for name, addr in WATCH8:
        out.append("    %-26s = %d" % (name, r8(addr)))
    for name, addr in WATCH32:
        out.append("    %-26s = %d" % (name, r32(addr)))
    off1, hp1 = r16(310), r16(1443)
    ref = r16(39)
    out.append("    -- 推算: 无偏移高压1 = %d, 冷凝1 = %.1f C"
               % (hp1 - off1, pt.pt_temp(ref, hp1) if 0 <= ref <= 3 else float("nan")))
    return "\n".join(out)


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    def connect():
        ss = ConnectHelper.session_with_chosen_probe(
            target_override="stm32f103rc",
            options={"frequency": 1000000, "connect_mode": "attach"},
        )
        ss.open()
        tt = ss.target
        if tt.get_state() == tt.State.HALTED:
            say("!! 连接时 HALTED —— 已 resume")
            tt.resume()
        return ss, tt

    session, tgt = connect()
    say(f"已连接 state={tgt.get_state().name}")
    say()
    say("=== 复位前 ===")
    before = read_all(tgt)
    say(before)
    session.close()

    if DRY:
        say()
        say("(--dry-run，不复位)")
        _write()
        return 0

    # 等一会儿，让参数存盘门控跑过（EEPROM 写入）
    say()
    say("等 20 秒让参数存盘 ...")
    time.sleep(20)

    # ---- 复位 ----
    say()
    say(">>> 执行 tgt.reset()（复位并运行）")
    session, tgt = connect()
    tgt.reset()
    time.sleep(0.8)
    st = tgt.get_state()
    say(f"    复位后立即 state={st.name}")
    if st == tgt.State.HALTED:
        say("    !! 落在 HALTED —— resume 放开")
        tgt.resume()
        time.sleep(0.5)
    # 连续确认它确实在跑
    for i in range(10):
        time.sleep(0.6)
        st = tgt.get_state()
        if st == tgt.State.HALTED:
            say(f"    !! 第 {i + 1} 次查发现 HALTED —— 再 resume")
            tgt.resume()
        else:
            say(f"    持续确认 state={st.name}")
    session.close()
    say("已断开（复位完成）")

    # ---- 复位后重新连上读回 ----
    say()
    say("等 8 秒让 316 重新初始化，再连上读回 ...")
    time.sleep(8)
    try:
        session, tgt = connect()
        say(f"已重连 state={tgt.get_state().name}")
        say()
        say("=== 复位后 ===")
        after = read_all(tgt)
        say(after)
        session.close()

        # ---- 对比 ----
        def parse(block: str) -> dict[str, str]:
            d = {}
            for line in block.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    d[k.strip().lstrip("- ").strip()] = v.strip()
            return d

        b, a = parse(before), parse(after)
        say()
        say("=== 对比（只看变化的）===")
        for k in b:
            if b[k] != a.get(k):
                say("    %-26s  %s  ->  %s" % (k, b[k], a.get(k)))
        off_b = b.get("AI0 偏移 (AI0 1#高压)")
        off_a = a.get("AI0 偏移 (AI0 1#高压)")
        say()
        if off_b == off_a:
            say(">>> AI0 偏移复位后**还在**（%s）：偏移进了 EEPROM，能扛住复位 ✓" % off_a)
        else:
            say(">>> AI0 偏移复位后**丢了**（%s -> %s）：偏移只是 RAM，复位就没了 ✗" % (off_b, off_a))
            say("    原因：Parameter[350]=12641(MAGIC) 让 OutdoorAiConfigMigrate() 不再执行，")
            say("    所以不会再从 UserA0ValueSet(499) 恢复。")
    except Exception as exc:  # noqa: BLE001
        say(f"!! 复位后重连失败: {exc}")

    _write()
    return 0


def _write() -> None:
    (pathlib.Path(__file__).resolve().parent / "reset_316.txt").write_text(
        "\n".join(LINES) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
