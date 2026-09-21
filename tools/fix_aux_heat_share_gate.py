# -*- coding: utf-8 -*-
"""修「热泵制热下、〖制热与再热/辅热是否共用〗=否 时辅热被整体禁用」。

规格书依据（`code/scratch_spec.txt`，§3.1 备注 + §3.6）：

  备注 3B：〖制热方式〗为"热泵制热"时，〖再热/辅热方式〗中选项均指辅热，
           此时〖再热是否启用〗选"是"时再热/辅热共用且〖再热/辅热方式〗不能为"无"。
           ⇒ 辅热的条件只有三条：热泵制热 + 再热是否启用=是 + 方式≠无。**没有"共用"**。

  备注 4：〖制热与再热/辅热是否共用〗选否时，制热与再热/辅热不能同时选分段电加热器。
           ⇒ 这是限制式写法，**预设了"选否时其余组合都成立"**；
             它是"共用"在规格书里**唯一**被定义的后果。
           ⇒ 且它要求 HeatModeSet ∈ {3,4,5}，**在热泵制热(==1)下根本不适用**。

原代码 `HeatReheatShareSet != 0` 把"共用=否"从"不能都选分段"放大成"辅热整体禁用"：
outputMode 留在 HEAT_OUTPUT_NONE ⇒ 下方守卫 `outputMode == HEAT_OUTPUT_NONE` 直接
全清并 return ⇒ 连 §3.6 明写的「化霜开始→辅热全开」都做不到。

改法：删掉该条件，`heatAllow` 改用 `separateStageConflict`（与制冷分支对称）。
热泵制热时 `separateStageConflict` 恒为 0，**不改变本分支原有行为**。

⚠ 不要"把化霜分支提到守卫之前" —— 守卫挡的是 SysStep!=2 / 通风消毒排毒模式 /
   MainHeatFaultLatch，那几种情况辅热本来就该关（§3.1「通风：加热装置不开启」）。
   去掉 `HeatReheatShareSet != 0` 后 outputMode 不再为 NONE，化霜分支自然可达。

⚠ 本文件是混合编码，**必须字节级改**，绝不能用 Edit（见 firmware-repos-mixed-encodings）。
⚠ 同拨版本号：V10.9 -> V10.10。

跑法：
    python.exe tools/fix_aux_heat_share_gate.py            # 干跑
    python.exe tools/fix_aux_heat_share_gate.py --apply    # 真改
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
        print("  [FAIL] %-44s 锚点命中 %d 次（预期 1）" % (label, n))
        problems.append(label)
        return data
    print("  [OK  ] %-44s" % label)
    return data.replace(old, new)


# ---- 编辑 1：删掉 (HeatReheatShareSet != 0) --------------------------------
OLD1 = (b"\t\t\tif(ReheatEnableSet &&\r\n"
        b"\t\t\t   (HeatReheatShareSet != 0) &&\r\n"
        b"\t\t\t   (ReheatModeSet != HEAT_OUTPUT_NONE))\r\n"
        b"\t\t\t{\r\n"
        b"\t\t\t\toutputMode = ReheatModeSet;\r\n"
        b"\t\t\t\theatAllow = IndoorHeatPumpFullLoad();\r\n"
        b"\t\t\t}")

NEW1 = (
    "\t\t\t/*\r\n"
    "\t\t\t * 2026-09-20：删掉 (HeatReheatShareSet != 0)。\r\n"
    "\t\t\t * 规格书 §3.1 备注 3B 给辅热的条件只有三条：制热方式=热泵制热、\r\n"
    "\t\t\t * 再热是否启用=是、再热/辅热方式≠无，没有\"共用\"这一项。\r\n"
    "\t\t\t * 备注 4 对\"共用\"唯一定义的后果是\"共用=否 时制热与再热/辅热不能\r\n"
    "\t\t\t * 同时选分段电加热器\"，不是\"辅热不能跑\"；且它要求 HeatModeSet∈{3,4,5}，\r\n"
    "\t\t\t * 在热泵制热(==1)下根本不适用。\r\n"
    "\t\t\t * 原条件把\"共用=否\"放大成\"辅热整体禁用\"，outputMode 留在 NONE ⇒\r\n"
    "\t\t\t * 下方守卫 `outputMode == HEAT_OUTPUT_NONE` 直接全清并 return ⇒\r\n"
    "\t\t\t * 连 §3.6 的\"化霜开始→辅热全开\"都做不到。\r\n"
    "\t\t\t * 改用 separateStageConflict，与制冷分支对称；热泵制热时它恒为 0。\r\n"
    "\t\t\t */\r\n"
    "\t\t\tif(ReheatEnableSet &&\r\n"
    "\t\t\t   (ReheatModeSet != HEAT_OUTPUT_NONE))\r\n"
    "\t\t\t{\r\n"
    "\t\t\t\toutputMode = ReheatModeSet;\r\n"
    "\t\t\t\theatAllow = separateStageConflict ? 0 : IndoorHeatPumpFullLoad();\r\n"
    "\t\t\t}"
).encode("utf-8")

# ---- 编辑 2/3：User.h 拨版本号 + 注释 --------------------------------------
OLD2 = b"#define PSC330_VERSION_MINOR        9"
NEW2 = b"#define PSC330_VERSION_MINOR        10"

ANCHOR3 = b"   */\r\n#define PSC330_VERSION_MODEL        330"
NOTE3 = (
    "   V10.9 -> V10.10 (2026-09-20)：修热泵制热下〖制热与再热/辅热是否共用〗=否 时\r\n"
    "   辅热被整体禁用。规格书备注 3B 给辅热的条件只有三条（热泵制热 / 再热是否启用=是 /\r\n"
    "   再热辅热方式≠无），没有\"共用\"；备注 4 对\"共用\"唯一定义的后果是\"共用=否 时制热与\r\n"
    "   再热/辅热不能同时选分段电加热器\"，且它在热泵制热下不适用。原条件的 outputMode 留在\r\n"
    "   NONE ⇒ 下方守卫全清并 return ⇒ 连 §3.6 的\"化霜开始→辅热全开\"都做不到。\r\n"
    "   改用 separateStageConflict，与制冷分支对称。\r\n"
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
    ua = swap(ua, OLD1, NEW1, "UserAction.c 删 HeatReheatShareSet 门槛")
    uh = swap(uh, OLD2, NEW2, "User.h VERSION_MINOR 9 -> 10")
    if b"V10.9 -> V10.10" in uh:
        print("  [SKIP] %-44s" % "User.h 版本注释（已追加）")
    else:
        uh = swap(uh, ANCHOR3, NOTE3, "User.h 版本注释追加")

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
