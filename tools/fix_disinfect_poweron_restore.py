# -*- coding: utf-8 -*-
"""修「掉电前处于消毒/排毒/消排毒 ⇒ 来电自启必然不成立」。

## 缺陷机制

```
UserAction()            UserAction.c:3369  InitCount 到 5 秒就调 IndoorDisinfectExhaustAction()
SwitchStatusProcess()   Switch.c:86        Systick_1ms < 20000（20 秒）就一直 return
                        ↓  中间 t=5s..20s 这 15 秒窗口
IndoorDisinfectExhaustAction()  UserAction.c:1605
                        if((SysStatus != NORRUN) && (SysStatus != TIMERUN))
                        { IndoorEmergencyStopLoads(); ... return; }   // SysStatus 此时 = DLAY
IndoorEmergencyStopLoads()      UserAction.c:348   SysStatusLoader = 0;   ← 被提前清掉
                        ↓
Switch.c:99             if((UserAutoModeSet==1)&&(UserSwitchSet==0)&&(SysStatusLoader))
                        ⇒ 不成立 ⇒ 来电自启作废
```

⇒ 只要 EEPROM 里 `[236] UserWorkModeSetTEMP` 是 3/4/5（掉电前正是消毒/排毒/消排毒），
来电自启**必然**不生效，连 `Switch.c:101-105` 的"降级为 LastNormalModeSet"分支也走不到。

自相矛盾之处：`Switch.c:101-105` 专门写了把 3/4/5 降级的代码，说明作者本就预期
EEPROM 里会有 3/4/5。

制冷/制热/通风**不受影响** —— 它们在 `UserAction.c:1585` 那条分支就 return 了，不碰 SysStatusLoader。

## 修法

在 `IndoorDisinfectExhaustAction()` 最前面加一句，**上电 20 秒内直接返回**。
判据用与 `Switch.c:86` **完全相同**的表达式 `Systick_1ms < 20000`，两边可证明是对齐的。

上电 20 秒内 `SysStep` 恒为 0、所有负载本就未启动，跳过本函数无副作用
（本函数所有分支都只是"复位"或"硬停"，没有一个分支会启动什么）。

⚠ `UserAction.c` 是**混合编码**，**必须字节级改**，绝不能用 Edit。
⚠ 按既定规矩同拨版本号：V10.11 -> V10.12。

跑法：
    python.exe tools/fix_disinfect_poweron_restore.py            # 干跑
    python.exe tools/fix_disinfect_poweron_restore.py --apply    # 真改
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
    print("  [OK  ] %-46s  -%d/+%d 字节" % (label, len(old), len(new)))
    return data.replace(old, new)


# ---- 编辑 1：IndoorDisinfectExhaustAction 最前面加上电 20 秒闸门 -------------
# 锚点必须够长：单独一行 `\tunsigned char exhaustFan;\r\n` 在 IndoorNormalStartSequence
# 里也有一份（偏移 0xa441），只有接上后面的 if 才唯一。
ANCHOR1 = (
    b"\tunsigned char supplyFan;\r\n"
    b"\tunsigned char exhaustFan;\r\n"
    b"\tif((UserWorkModeSetTEMP != MODE_DISINFECT) && (UserWorkModeSetTEMP != MODE_EXHAUST) "
    b"&& (UserWorkModeSetTEMP != MODE_AUTO_DISINFECT))\r\n"
)

NEW1 = (
    "\tunsigned char supplyFan;\r\n"
    "\tunsigned char exhaustFan;\r\n"
    "\t/*\r\n"
    "\t * 2026-09-20：上电 20 秒内不要走下面任何分支。\r\n"
    "\t * Switch.c:86-91 在 Systick_1ms<20000 期间把 SysStatus 置成 DLAY 并直接 return，\r\n"
    "\t * 也就是说「来电自启」的判定要等到 20 秒才做；而本函数从第 5 秒（UserAction 的\r\n"
    "\t * InitCount>=5）就开始跑。中间这 15 秒里只要落到下面「非运行态硬停」那条分支，\r\n"
    "\t * 就会调 IndoorEmergencyStopLoads()（UserAction.c:348 `SysStatusLoader = 0`），\r\n"
    "\t * 把「掉电前是否在开机」这个唯一判据在 Switch.c:99 读它之前清掉。\r\n"
    "\t *\r\n"
    "\t * 后果：掉电前模式是消毒/排毒/消排毒（[236] ∈ {3,4,5}）时，来电自启必然不成立，\r\n"
    "\t * 连 Switch.c:101-105 的「降级为 LastNormalModeSet」分支也走不到。\r\n"
    "\t * （制冷/制热/通风不受影响 —— 它们在下面第一条分支就 return，不碰 SysStatusLoader。）\r\n"
    "\t *\r\n"
    "\t * 上电 20 秒内 SysStep 恒为 0、所有负载本就未启动，跳过本函数无副作用。\r\n"
    "\t * 判据刻意用与 Switch.c:86 完全相同的表达式，两边可证明是对齐的。\r\n"
    "\t */\r\n"
    "\tif(Systick_1ms < 20000)return;\r\n"
    "\tif((UserWorkModeSetTEMP != MODE_DISINFECT) && (UserWorkModeSetTEMP != MODE_EXHAUST) "
    "&& (UserWorkModeSetTEMP != MODE_AUTO_DISINFECT))\r\n"
).encode("utf-8")

# ---- 编辑 2：版本号 V10.11 -> V10.12 ---------------------------------------
OLD2 = b"#define PSC330_VERSION_MINOR        11"
NEW2 = b"#define PSC330_VERSION_MINOR        12"

ANCHOR3 = b"   */\r\n#define PSC330_VERSION_MODEL        330"
NOTE3 = (
    "   V10.11 -> V10.12 (2026-09-20)：修「掉电前处于消毒/排毒/消排毒 ⇒ 来电自启必然不成立」。\r\n"
    "   机制：IndoorDisinfectExhaustAction() 从第 5 秒就跑，而 Switch.c 的来电自启判定要到\r\n"
    "   第 20 秒（Systick_1ms<20000 期间 SysStatus=DLAY）；中间落进「非运行态硬停」分支会调\r\n"
    "   IndoorEmergencyStopLoads()，它把 SysStatusLoader(=来电自启的唯一判据) 提前清 0。\r\n"
    "   修法：本函数最前面加 `if(Systick_1ms < 20000)return;`，与 Switch.c:86 同一判据。\r\n"
    "   */\r\n#define PSC330_VERSION_MODEL        330"
).encode("utf-8")


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def main() -> int:
    apply = "--apply" in sys.argv

    ua = UA.read_bytes()
    uh = UH.read_bytes()
    orig_len, orig_lines = len(ua), ua.count(b"\r\n")
    orig_uh, orig_fffd_ua, orig_fffd_uh = len(uh), ua.count(b"\xef\xbf\xbd"), uh.count(b"\xef\xbf\xbd")
    print("改前：")
    print("  UserAction.c  sha=%s  bytes=%d  U+FFFD=%d  CRLF=%d"
          % (sha(UA), len(ua), ua.count(b"\xef\xbf\xbd"), ua.count(b"\r\n")))
    print("  User.h        sha=%s  bytes=%d  U+FFFD=%d"
          % (sha(UH), len(uh), uh.count(b"\xef\xbf\xbd")))
    print()

    print("编辑：")
    ua = swap(ua, ANCHOR1, NEW1, "UserAction.c 加上电 20 秒闸门")
    uh = swap(uh, OLD2, NEW2, "User.h VERSION_MINOR 11 -> 12")
    if b"V10.11 -> V10.12" in uh:
        print("  [SKIP] %-46s" % "User.h 版本注释（已追加）")
    else:
        uh = swap(uh, ANCHOR3, NOTE3, "User.h 版本注释追加")

    if problems:
        print("\n[X] 有锚点没命中，未写入任何文件。")
        return 1

    # 自检：编码没坏（U+FFFD 一个都不许新增）
    if ua.count(b"\xef\xbf\xbd") != orig_fffd_ua or uh.count(b"\xef\xbf\xbd") != orig_fffd_uh:
        print("\n[X] U+FFFD 数变了，未写入。")
        return 1

    print()
    print("改后：")
    print("  UserAction.c  bytes=%d (%+d)  lines=%d (%+d)  U+FFFD=%d"
          % (len(ua), len(ua) - orig_len, ua.count(b"\r\n") + 1,
             ua.count(b"\r\n") - orig_lines, ua.count(b"\xef\xbf\xbd")))
    print("  User.h        bytes=%d (%+d)  U+FFFD=%d"
          % (len(uh), len(uh) - orig_uh, uh.count(b"\xef\xbf\xbd")))

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
