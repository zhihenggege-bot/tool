# -*- coding: utf-8 -*-
"""修「可控硅模式下预热两路开关量 Y15/Y16 从不吸合」。

根因：IndoorEnforceConfiguredOutputDisable() 的白名单只列了
HEAT_OUTPUT_STAGE_1_2(2) / HEAT_OUTPUT_STAGE_1_2_4(3)，**漏了 HEAT_OUTPUT_SCR(4)**，
于是 SCR 模式每扫描无条件清 Y15/Y16/Y17。而 main() 的死循环是

    while(1){ SystemAction();  /* WriteOutput(): output[]->GPIO */  User(); }

WriteOutput() 在 User() 之前 ⇒ GPIO 每轮锁存到的都是上一轮末尾（=清完之后）的值
⇒ 引脚恒为 0，继电器一次都不吸。AO(DA1) 因为紧邻的 `!= AO && != SCR` 分支被排除、
没人清，所以留在 10V —— 这就是"只有 AO 有输出"的由来。

V10.7 引入 SCR 时同类的三处守卫改了两处（reheatUsesStage、separateStageConflict），
唯独漏了这处 —— 偏偏只有这处会真清引脚。

改法：把 HEAT_OUTPUT_SCR 加进白名单。安全 —— 该关的时候 PreHeatControl()
自己在提前返回分支里会清（UserAction.c:3073），IndoorStopHeatPreheatLoads() 也清。

⚠ 本文件是混合编码，**必须字节级改**，绝不能用 Edit（见 firmware-repos-mixed-encodings）。
⚠ 按规矩同拨版本号。**跳号到 V10.9**：V10.8 是 §26.4 那次未拨版本号的失败尝试（已回退），
   用一个号会和它撞名。

跑法：
    python.exe tools/fix_scr_preheat_do_whitelist.py            # 干跑
    python.exe tools/fix_scr_preheat_do_whitelist.py --apply     # 真改
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


# ---- 编辑 1：UserAction.c 白名单加 SCR ------------------------------------
OLD1 = (b"\tif((PreheatModeSet != HEAT_OUTPUT_STAGE_1_2) &&\r\n"
        b"\t   (PreheatModeSet != HEAT_OUTPUT_STAGE_1_2_4))\r\n")

NEW1 = (
    "\t/*\r\n"
    "\t * 2026-09-20：白名单原来只列了 STAGE_1_2(2)/STAGE_1_2_4(3)，漏了\r\n"
    "\t * HEAT_OUTPUT_SCR(4) => 可控硅模式每扫描把 Y15/Y16/Y17 清掉，\r\n"
    "\t * 而 WriteOutput() 在 User() 之前锁存 GPIO => 引脚恒为 0、继电器不吸。\r\n"
    "\t * 补上 SCR。该关的时候 PreHeatControl() 自己的提前返回分支会清。\r\n"
    "\t */\r\n"
    "\tif((PreheatModeSet != HEAT_OUTPUT_STAGE_1_2) &&\r\n"
    "\t   (PreheatModeSet != HEAT_OUTPUT_STAGE_1_2_4) &&\r\n"
    "\t   (PreheatModeSet != HEAT_OUTPUT_SCR))\r\n"
).encode("utf-8")

# ---- 编辑 2：User.h 拨版本号 ---------------------------------------------
OLD2 = b"#define PSC330_VERSION_MINOR        7"
NEW2 = b"#define PSC330_VERSION_MINOR        9"

# ---- 编辑 3：User.h 版本注释 ---------------------------------------------
ANCHOR3 = b"   */\r\n#define PSC330_VERSION_MODEL        330"
NOTE3 = (
    "   V10.7 -> V10.9 (2026-09-20)：修可控硅模式下预热两路开关量 Y15/Y16 从不吸合。\r\n"
    "   IndoorEnforceConfiguredOutputDisable() 的白名单只列了 STAGE_1_2(2)/STAGE_1_2_4(3)，\r\n"
    "   漏了 HEAT_OUTPUT_SCR(4) ⇒ SCR 模式每扫描无条件清 Y15/Y16/Y17；而 WriteOutput()\r\n"
    "   在 User() 之前锁存 GPIO ⇒ 引脚恒为 0。V10.7 引入 SCR 时另外两处同类守卫都改了，\r\n"
    "   唯独漏了这处。AO(DA1) 因紧邻分支把 SCR 排除、没人清，所以留在 10V。\r\n"
    "   跳号 V10.8：那是未拨版本号的失败尝试（已回退），避免与本次撞名。\r\n"
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
    ua = swap(ua, OLD1, NEW1, "UserAction.c 白名单加 HEAT_OUTPUT_SCR")
    uh = swap(uh, OLD2, NEW2, "User.h VERSION_MINOR 7 -> 9")
    if b"V10.7 -> V10.9" in uh:
        print("  [SKIP] %-46s" % "User.h 版本注释（已追加）")
    else:
        uh = swap(uh, ANCHOR3, NOTE3, "User.h 版本注释追加")

    if problems:
        print("\n✗ 有锚点没命中，未写入任何文件。")
        return 1

    print()
    print("改后：")
    print("  UserAction.c  bytes=%d (+%d)  U+FFFD=%d" % (len(ua), len(ua) - UA.stat().st_size, ua.count(b"\xef\xbf\xbd")))
    print("  User.h        bytes=%d (+%d)  U+FFFD=%d" % (len(uh), len(uh) - UH.stat().st_size, uh.count(b"\xef\xbf\xbd")))

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
