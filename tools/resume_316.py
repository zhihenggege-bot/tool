"""把被 pyocd 默认 halt 冻住的 316 放开（只做这一件事，不采样）。

背景：pyocd 的 `session.open()` 默认 `connect_mode="halt"`，一连上就停内核。
2026-09-17 读活变量时把台面上的 316 冻住过一次。

本脚本用 `connect_mode="attach"`（只挂总线、不改内核状态）连上去，
检查状态，发现 HALTED 就 `resume()` 放开，然后**再确认一次它确实在跑**。

跑法：
    python.exe tools/resume_316.py
"""

from __future__ import annotations

import pathlib
import sys
import time

LINES: list[str] = []


def line(s: str = "") -> None:
    LINES.append(s)


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f103rc",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        line("!! 没找到 ST-Link")
        _write()
        return 1

    session.open()
    tgt = session.target
    st = tgt.get_state()
    line(f"已连接（attach）-> {tgt.part_number}   进入时 state = {st.name}")

    if st == tgt.State.HALTED:
        line("内核是 HALTED —— 执行 resume()")
        tgt.resume()
        time.sleep(0.3)
        st2 = tgt.get_state()
        line(f"resume 后 state = {st2.name}")
        if st2 != tgt.State.RUNNING:
            line("!! 仍未 RUNNING —— 可能需要断电重启")
    else:
        line("内核本来就在跑（或非 HALTED），没有动它")

    # 停 2 秒再确认一次，别是"刚放开又停了"
    for _ in range(4):
        time.sleep(0.5)
        line(f"  持续确认 state = {tgt.get_state().name}")

    session.close()
    line("已断开")

    # ---- 从 330 侧确认外机是否恢复在线 ----
    line()
    line("=== 从 330 侧看外机是否恢复（COM6）===")
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                               / "psc330_monitor_tool" / "psc330_monitor"))
        import app as m

        c = m.ModbusRtuClient()
        c.open("COM6", m.DEFAULT_BAUD)

        def rd(a: int, n: int = 1):
            for _ in range(3):
                try:
                    return c.read_holding_registers(1, a, n)
                except Exception:  # noqa: BLE001
                    time.sleep(0.2)
            return [-1] * n

        try:
            for u in (1, 2):
                b = m.OUTDOOR_GATEWAY_BASE + (u - 1) * m.OUTDOOR_GATEWAY_STEP
                online = rd(b + 42)[0]
                wstate = rd(b + 43)[0]
                err = rd(b + 44)[0]
                line(f"  {u}#外机: 在线={online}  写状态={wstate}  错误码={err}")
            line(f"  330[700] SysStatus={rd(700)[0]}  330[709] SysStep={rd(709)[0]}")
        finally:
            c.close()
    except Exception as exc:  # noqa: BLE001
        line(f"  !! 串口读取失败: {exc}")

    _write()
    return 0


def _write() -> None:
    p = pathlib.Path(__file__).resolve().parent / "resume_316.txt"
    p.write_text("\n".join(LINES) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
