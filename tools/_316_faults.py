"""读 316（外机1）的故障字 + 化霜参数 + 压机使能，判断定时化霜能不能进。

只读，pyocd attach 模式（绝不停核）。
"""
from __future__ import annotations

import sys

PARAM_BASE = 0x2000164A
TARGET = "stm32f103rc"

# COMPERR = 605
COMPERR = 605
FAULTS = [
    (1, "Comp1HightPressErr 高压开关/压力"),
    (2, "Comp2HightPressErr"),
    (3, "AI0TempErr   1#高压探头"),
    (4, "AI1TempErr   ?"),
    (5, "AI2TempErr   2#高压探头"),
    (6, "AI3TempErr   ?"),
    (7, "?"),
    (8, "Fin1TempErr  翅片1探头   <<< 会破坏化霜结束判据"),
    (9, "Fin2TempErr  翅片2探头   <<< 同上"),
    (10, "Exhaust1TempErr 排气1探头 <<< 推荐"),
    (11, "?"),
    (12, "XiQi1TempErr  吸气1探头   <<< 推荐"),
    (13, "?"),
    (14, "?"),
    (15, "Exhaust2/XiQi2 ?"),
]

DEFROST = [
    (182, "环境温度定时化霜温度设定值", 0.1),
    (183, "环境温度定时化霜时间间隔 分", 1),
    (184, "环境温度定时化霜时间 分", 1),
    (185, "化霜开始前压缩运转最小时间 分", 1),
    (186, "化霜开始前翅片温度", 0.1),
    (187, "环境温度与翅片温度差", 0.1),
    (188, "环温>0 两次化霜间隔 分", 1),
    (189, "环温<0 两次化霜间隔 分", 1),
    (190, "化霜结束室外机翅片温度", 0.1),
    (191, "环温>0 化霜时间 分", 1),
    (192, "环温<0 化霜时间 分", 1),
]


def main() -> int:
    from pyocd.core.helpers import ConnectHelper

    session = ConnectHelper.session_with_chosen_probe(
        target_override=TARGET, options={"frequency": 1000000, "connect_mode": "attach"})
    if session is None:
        print("!! 没找到 ST-Link")
        return 1
    session.open()
    tgt = session.target
    if tgt.get_state() == tgt.State.HALTED:
        print("!! 进入时 HALTED —— 已 resume")
        tgt.resume()

    def p(i):
        b = tgt.read_memory_block8(PARAM_BASE + i * 2, 2)
        v = b[0] | (b[1] << 8)
        return v - 0x10000 if v & 0x8000 else v

    print("=== 316 外机1：版本 ===")
    print("  Parameter[1000..1005] =", [p(1000 + i) for i in range(6)])
    print("  机型[165] =", p(165), "  风机类型[166] =", p(166))
    print("  PressSensor[107] =", p(107), " (1=高低压都有, 2=只低压)")
    print()
    print("=== 压机使能与运行 ===")
    print("  COMPRUN=150 -> [152] Comp1Enable =", p(152), " (0=使能中, 1=禁用)")
    print("                   [153] Comp2Enable =", p(153))
    print()
    print("=== 故障字 Parameter[605..620]（COMPERR=605）===")
    any_fault = False
    for off, nm in FAULTS:
        v = p(COMPERR + off)
        if v:
            any_fault = True
        print("  [%3d] = %-3d %s" % (COMPERR + off, v, nm))
    print()
    print(">>> 有非零故障字" if any_fault else ">>> **全部为 0 —— 没有任何传感器故障**")
    print()
    print("=== 化霜参数 ===")
    for idx, nm, sc in DEFROST:
        v = p(idx)
        shown = "%.1f" % (v / 10.0) if sc == 0.1 else str(v)
        print("  [%3d] %-32s = %s" % (idx, nm, shown))

    if tgt.get_state() == tgt.State.HALTED:
        print("!! 结束 HALTED —— resume")
        tgt.resume()
    print("结束 state=%s" % tgt.get_state().name)
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
