# -*- coding: utf-8 -*-
"""PSC330 内机：按规格书原文修三处「确定不符合」+ 拨版本号 V10.13。

对照报告 `调试记录_规格书对照_第1-3章_20260920.md` §45 复核后的清单，
这几条是**回规格书原文逐字核对过、判定成立**的：

## ① §3.3.4【排毒】"开送风机、排风机（两者顺序根据送排风机间隔时间）"

原实现 `IndoorSpecialFanStartTimeline()` 先取绝对值：

    fanDelay = (fanInterval < 0) ? (unsigned int)(-fanInterval) : (unsigned int)fanInterval;
    ...
    *exhaustStart = 0;          /* 排风机固定 t=0 先起 */
    *supplyStart = fanDelay;    /* 送风机永远延后 */

⇒ **符号被丢掉，顺序选不出来**（消排毒的第二阶段同样受害）。

修法：保留符号，约定与正常开关机路径一致（[328] 正负语义）——
**正值排风先开、负值送风先开**。
自洽性：step6 的"逆序停风机"用的是 `sequenceEnd - start`，符号保留后
先开的那个会自然变成后停，无需另改。

## ② §3.3.1/§3.3.3 排风机与送风机间隔「30s（±60s可调）」

规格书原文给的是 **±60s**，代码允许并钳到 **±90s**（`user.c` 参数表 + clamp），
超出规格 50%。用户 2026-09-21 裁定：**按规格书取 ±60**。

改两处：`UserAction.c` 的 clamp、`user.c` 的参数上下限表。
（消排毒路径 `if(fanDelay > 60)fanDelay = 60` 本来就是 60，不用动。）

## ③ §3.1〖混风阀〗/〖排风阀〗"此项选择要求新风阀根据 CO2 浓度及新回风焓差控制"

代码只校了"新风阀是 0-10V"，**没校调节依据**：

    mixValveValid = ((MixAirValveTypeSet == 1) && (FreshValveModeSet == VALVE_OUTPUT_AO)) ? 1 : 0;

按规格书补上 `FreshValveCtrlBasisSet == 1`（= "CO2及新回风焓差"，
`FRESH_VALVE_BASIS_MAP` 与 `User.h:715` 均可证）。
⚠ **上位机监控工具早就在校这一条**（`app.py:5141`），是固件漏了 —— 属补平。

## 为什么用字节级补丁

固件仓**编码按区域混**（同一文件 GBK 中文注释 + ASCII 代码，LF/CRLF 并存），
Edit 类工具会把解不开的字节烧成 U+FFFD（实测毁过 UserAction.c 132 处）。
本脚本只匹配**纯 ASCII 锚点、只插入纯 ASCII**，改完自检**非 ASCII 字节总数一字不变**。

跑法： python.exe tools/patch_330_spec_fixes.py [--check]
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = ROOT / "PSC330RK-V10-内机" / "User" / "UserSrc" / "UserAction.c"
UC = ROOT / "PSC330RK-V10-内机" / "User" / "UserSrc" / "user.c"
UH = ROOT / "PSC330RK-V10-内机" / "User" / "UserHead" / "User.h"

# ---- ① 排毒/消排毒 排毒段：保留符号 ----
OLD_ORDER = (b"\t*exhaustStart = 0;\r\n"
             b"\t*supplyStart = fanDelay;\r\n"
             b"\t*sequenceEnd = fanDelay;\r\n")
NEW_ORDER = (b"\t/* Specification 3.3.4: for EXHAUST (and the exhaust half of\n"
             b"\t   AUTO_DISINFECT) the order of supply vs exhaust fan follows the signed\n"
             b"\t   [328] interval. The old code took abs() first and then pinned the\n"
             b"\t   exhaust fan to t=0, so the order could never be selected.\n"
             b"\t   Convention matches the normal start/stop path: positive -> exhaust\n"
             b"\t   first, negative -> supply first. step 6 reverses the stop order via\n"
             b"\t   (sequenceEnd - start), so keeping the sign is enough. */\n"
             b"\tif(fanInterval >= 0)\n"
             b"\t{\n"
             b"\t\t*exhaustStart = 0;\n"
             b"\t\t*supplyStart = fanDelay;\n"
             b"\t}\n"
             b"\telse\n"
             b"\t{\n"
             b"\t\t*supplyStart = 0;\n"
             b"\t\t*exhaustStart = fanDelay;\n"
             b"\t}\n"
             b"\t*sequenceEnd = fanDelay;\r\n")

# ---- ② [328] ±90 -> ±60 ----
OLD_CLAMP = b"\tif(delay > 90)delay = 90;\r\n\telse if(delay < -90)delay = -90;\r\n"
NEW_CLAMP = (b"\t/* Specification gives 30s (+/-60s adjustable); the code used to allow\n"
             b"\t   and clamp to +/-90, 50% wider than the spec. */\n"
             b"\tif(delay > 60)delay = 60;\r\n\telse if(delay < -60)delay = -60;\r\n")
OLD_TABLE = b"Parameter_max[328]=90;   Parameter_min[328]=-90;"
NEW_TABLE = b"Parameter_max[328]=60;   Parameter_min[328]=-60;"

# ---- ③ 混风阀 / 排风阀 前置条件 ----
OLD_MIX = (b"\tmixValveValid = ((MixAirValveTypeSet == 1) &&\r\n"
           b"\t\t(FreshValveModeSet == VALVE_OUTPUT_AO)) ? 1 : 0;\r\n")
NEW_MIX = (b"\t/* Specification: enabling the mixing valve requires the fresh-air valve to\n"
           b"\t   be controlled by CO2 and the fresh/return enthalpy difference, i.e.\n"
           b"\t   FreshValveCtrlBasisSet == 1. The code only checked that it was AO.\n"
           b"\t   (The HMI tool already enforced this - app.py:5141.) */\n"
           b"\tmixValveValid = ((MixAirValveTypeSet == 1) &&\r\n"
           b"\t\t(FreshValveModeSet == VALVE_OUTPUT_AO) &&\r\n"
           b"\t\t(FreshValveCtrlBasisSet == 1)) ? 1 : 0;\r\n")
OLD_EXH = (b"\texhaustValveAOValid = ((ExhaustValveModeSet == VALVE_OUTPUT_AO) &&\r\n"
           b"\t\t(FreshValveModeSet == VALVE_OUTPUT_AO)) ? 1 : 0;\r\n")
NEW_EXH = (b"\t/* Same precondition as the mixing valve: the spec's bracket on the\n"
           b"\t   exhaust valve reads identically. */\n"
           b"\texhaustValveAOValid = ((ExhaustValveModeSet == VALVE_OUTPUT_AO) &&\r\n"
           b"\t\t(FreshValveModeSet == VALVE_OUTPUT_AO) &&\r\n"
           b"\t\t(FreshValveCtrlBasisSet == 1)) ? 1 : 0;\r\n")


def sub(raw: bytes, old: bytes, new: bytes, what: str) -> bytes:
    n = raw.count(old)
    if n != 1:
        raise SystemExit("锚点不唯一（%d 次）：%s" % (n, what))
    return raw.replace(old, new)


def patch_ua(raw: bytes) -> bytes:
    raw = sub(raw, OLD_ORDER, NEW_ORDER, "① IndoorSpecialFanStartTimeline 顺序")
    raw = sub(raw, OLD_CLAMP, NEW_CLAMP, "② [328] clamp")
    raw = sub(raw, OLD_MIX, NEW_MIX, "③ mixValveValid")
    raw = sub(raw, OLD_EXH, NEW_EXH, "③ exhaustValveAOValid")
    return raw


def patch_uc(raw: bytes) -> bytes:
    return sub(raw, OLD_TABLE, NEW_TABLE, "② [328] 参数表")


def patch_uh(raw: bytes) -> bytes:
    for a, b in ((b"#define PSC330_VERSION_MINOR        12",
                  b"#define PSC330_VERSION_MINOR        13"),
                 (b"#define PSC330_VERSION_DAY          20",
                  b"#define PSC330_VERSION_DAY          21")):
        raw = sub(raw, a, b, "版本号")
    anchor = b"*/\r\n#define PSC330_VERSION_MODEL        330"
    sub(raw, anchor, anchor, "版本日志注释结尾")
    log = (b"   V10.12 -> V10.13 (2026-09-21): three spec-conformance fixes, each verified\r\n"
           b"       against the original wording in the 260124 specification.\r\n"
           b"       1) 3.3.4 [EXHAUST] / [AUTO_DISINFECT] exhaust-half: the order of the\r\n"
           b"          supply vs exhaust fan now follows the signed [328] interval.\r\n"
           b"          IndoorSpecialFanStartTimeline() used to take abs() and then pin the\r\n"
           b"          exhaust fan to t=0, so 'supply first' could never be selected.\r\n"
           b"          step 6 reverses the stop order via (sequenceEnd - start), so keeping\r\n"
           b"          the sign is sufficient.\r\n"
           b"       2) 3.3.1/3.3.3 exhaust-vs-supply fan interval: spec says 30s (+/-60s\r\n"
           b"          adjustable); the code allowed and clamped +/-90. Now +/-60, in both\r\n"
           b"          the clamp in IndoorExhaustFanSignedDelay() and the parameter table.\r\n"
           b"       3) 3.1 [MIXING VALVE] / [EXHAUST VALVE]: the spec's bracket requires the\r\n"
           b"          fresh-air valve to be controlled by CO2 and the enthalpy difference.\r\n"
           b"          The code only checked for 0-10V (FreshValveModeSet == AO); it now also\r\n"
           b"          requires FreshValveCtrlBasisSet == 1. The HMI tool already enforced\r\n"
           b"          this (app.py:5141); the firmware did not.\r\n")
    return raw.replace(anchor, log + anchor)


def main() -> int:
    check = "--check" in sys.argv
    for path, fn in ((UA, patch_ua), (UC, patch_uc), (UH, patch_uh)):
        raw = path.read_bytes()
        before_hi = sum(1 for b in raw if b >= 0x80)
        before_lines = raw.count(b"\n")
        new = fn(raw) if not check else raw
        after_hi = sum(1 for b in new if b >= 0x80)
        print("%-14s 行 %d -> %d (+%d)   非ASCII字节 %d -> %d %s"
              % (path.name, before_lines, new.count(b"\n"),
                 new.count(b"\n") - before_lines, before_hi, after_hi,
                 "OK" if after_hi == before_hi else "**变了，中止**"))
        if after_hi != before_hi:
            raise SystemExit("!! 非 ASCII 字节数变了 —— 编码被破坏，中止")
        if not check:
            path.write_bytes(new)
    print("\n所有锚点唯一、编码未变。" if check else "\n已写入。下一步：编译 + 烧录 + 复测")
    return 0


if __name__ == "__main__":
    sys.exit(main())
