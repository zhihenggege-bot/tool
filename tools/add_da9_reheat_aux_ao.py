# -*- coding: utf-8 -*-
"""给「〖制热与再热/辅热是否共用〗= 否」补上再热/辅热的专用 AO（DA9）。

用户 2026-09-20 指令：
    共用 = 是  ⇒ 制热与再热/辅热共用一路 ⇒ 都走 DA0（不变）
    共用 = 否  ⇒ 再热/辅热 走专用 AO **DA9**；制热仍走 DA0

硬件依据（用户提供的 AO 点表）：
    AO4  0~10VDC  加热阀1/可控硅1（再热/辅热/制热）   → 固件 ReheatAO0 = DA[0]
    AO5  0~10VDC  加热阀2/可控硅2（新风预热）          → 固件 PreheatAO1 = DA[1]
    AO6  0~10VDC  加热阀3/可控硅3（制热）              → 固件 HeatAO9   = DA[9] ← 一直恒置 0
三路的宏名/注释与点表**逐条对得上**，说明这一路是硬件本来就有的，固件没实现。

为什么需要它：〖共用〗=否 意味着「两台独立加热器」。若两边都选 0-10V，
现有一路 DA0 无法分开驱动 ⇒ 两台的控制端只能并接、会一起调。
DA9 补上后，共用=否 + 双 0-10V 才有意义。而"都选分段"仍被
`separateStageConflict` 挡住（分段只有一组 DO 端子 —— 标书备注 4）。

只影响「再热/辅热」工况（制冷、或热泵制热）；非热泵制热(HeatModeSet>=2)仍走 DA0。

⚠ 行为变化：原本"共用=否 + 再热/辅热=0-10V"的组合，再热/辅热的输出口
   会从 DA0 **移到 DA9** —— 现场若已按 DA0 接线，需要改接。
⚠ 本文件是混合编码，**必须字节级改**，绝不能用 Edit。
⚠ 同拨版本号：V10.10 -> V10.11。

跑法：
    python.exe tools/add_da9_reheat_aux_ao.py            # 干跑
    python.exe tools/add_da9_reheat_aux_ao.py --apply    # 真改
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent / "PSC330RK-V10-内机"
UA = REPO / "User/UserSrc/UserAction.c"
UH = REPO / "User/UserHead/User.h"

problems: list[str] = []


def swap(data: bytes, old: bytes, new: bytes, label: str) -> bytes:
    n = data.count(old)
    if n != 1:
        print("  [FAIL] %-46s 锚点命中 %d 次（预期 1）" % (label, n))
        problems.append(label)
        return data
    print("  [OK  ] %-46s" % label)
    return data.replace(old, new)


# ---- 编辑 1：加 heatAO 变量 + 选口逻辑 -------------------------------------
OLD1 = b"\tunsigned char heatActive;\r\n\tunsigned char preheatActive;\r\n"

NEW1 = (
    "\tunsigned char heatActive;\r\n"
    "\tunsigned char preheatActive;\r\n"
    "\tvolatile uint16_t *heatAO = &ReheatAO0;\r\n"
    "\r\n"
    "\t/*\r\n"
    "\t * 2026-09-20：〖制热与再热/辅热是否共用〗=否 时，再热/辅热 走专用 AO(DA9)。\r\n"
    "\t * 硬件点表：AO4=可控硅1(再热/辅热/制热) → DA0、AO6=可控硅3(制热) → DA9。\r\n"
    "\t *   共用=是 ⇒ 制热与再热/辅热共用一路 ⇒ 都走 DA0（不变）\r\n"
    "\t *   共用=否 ⇒ 再热/辅热 独占 DA9；制热仍走 DA0\r\n"
    "\t * 只对「再热/辅热」工况生效（制冷、或热泵制热）；\r\n"
    "\t * 非热泵制热(HeatModeSet>=2)走的是「制热」，仍用 DA0。\r\n"
    "\t */\r\n"
    "\tif((HeatReheatShareSet == 0) &&\r\n"
    "\t   ((UserWorkModeSetTEMP == MODE_COOL) ||\r\n"
    "\t    ((UserWorkModeSetTEMP == MODE_HEAT) && (HeatModeSet == 1))))\r\n"
    "\t\theatAO = &HeatAO9;\r\n"
    "\r\n"
).encode("utf-8")

# ---- 编辑 2：把两处 &ReheatAO0 换成 heatAO ---------------------------------
OLD2 = (b"\t\t\t\t&ReheatAO0, &Heat1Y00, &Heat2Y01);\r\n"
        b"\t\telse\r\n"
        b"\t\t\tIndoorSetAO(&ReheatAO0, heatDemand);")

NEW2 = (b"\t\t\t\theatAO, &Heat1Y00, &Heat2Y01);\r\n"
        b"\t\telse\r\n"
        b"\t\t\tIndoorSetAO(heatAO, heatDemand);")

# ---- 编辑 3：改掉那句已过时的注释 ------------------------------------------
OLD3 = ("\t * 不再需要，已删除。DA9 在可控硅模式下不再使用（保留置 0）。").encode("utf-8")
NEW3 = ("\t * 不再需要，已删除。DA9 现作为「共用=否」时再热/辅热的专用 AO，"
        "见下方 heatAO 的选择。").encode("utf-8")

# ---- 编辑 4/5：User.h 版本号 + 注释 ----------------------------------------
OLD4 = b"#define PSC330_VERSION_MINOR        10"
NEW4 = b"#define PSC330_VERSION_MINOR        11"

ANCHOR5 = b"   */\r\n#define PSC330_VERSION_MODEL        330"
NOTE5 = (
    "   V10.10 -> V10.11 (2026-09-20)：给「〖制热与再热/辅热是否共用〗=否」补上再热/辅热的\r\n"
    "   专用 AO。共用=否 时 再热/辅热 走 DA9（硬件点表 AO6=可控硅3）、制热仍走 DA0；\r\n"
    "   共用=是 时仍共用 DA0、行为不变。只对再热/辅热工况生效（制冷 / 热泵制热）。\r\n"
    "   说明：共用=否 意为「两台独立加热器」，若两边都选 0-10V，原有单路 DA0 无法分开驱动。\r\n"
    "   ⚠ 行为变化：原「共用=否 + 再热/辅热=0-10V」组合的输出口由 DA0 移到 DA9，现场需改接。\r\n"
    "   */\r\n#define PSC330_VERSION_MODEL        330"
).encode("utf-8")


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def main() -> int:
    apply = "--apply" in sys.argv

    ua = UA.read_bytes()
    uh = UH.read_bytes()
    print("改前：")
    print("  UserAction.c  sha=%s  bytes=%d  U+FFFD=%d" % (sha(UA), len(ua), ua.count(b"\xef\xbf\xbd")))
    print("  User.h        sha=%s  bytes=%d  U+FFFD=%d" % (sha(UH), len(uh), uh.count(b"\xef\xbf\xbd")))
    print()

    print("编辑：")
    ua = swap(ua, OLD1, NEW1, "UserAction.c 加 heatAO + 选口逻辑")
    ua = swap(ua, OLD2, NEW2, "UserAction.c 两处 &ReheatAO0 -> heatAO")
    ua = swap(ua, OLD3, NEW3, "UserAction.c 改过时注释")
    uh = swap(uh, OLD4, NEW4, "User.h VERSION_MINOR 10 -> 11")
    if b"V10.10 -> V10.11" in uh:
        print("  [SKIP] %-46s" % "User.h 版本注释（已追加）")
    else:
        uh = swap(uh, ANCHOR5, NOTE5, "User.h 版本注释追加")

    if problems:
        print("\n✗ 有锚点没命中，未写入任何文件。")
        return 1

    print()
    print("改后：")
    print("  UserAction.c  bytes=%d (%+d)  U+FFFD=%d" % (len(ua), len(ua) - UA.stat().st_size, ua.count(b"\xef\xbf\xbd")))
    print("  User.h        bytes=%d (%+d)  U+FFFD=%d" % (len(uh), len(uh) - UH.stat().st_size, uh.count(b"\xef\xbf\xbd")))

    if apply:
        UA.write_bytes(ua)
        UH.write_bytes(uh)
        print("\n已写入：")
        print("  UserAction.c  sha=%s" % sha(UA))
        print("  User.h        sha=%s" % sha(UH))
    else:
        print("\n（干跑，未写入。加 --apply 生效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
