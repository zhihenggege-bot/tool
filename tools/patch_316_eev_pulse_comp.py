# -*- coding: utf-8 -*-
"""给 PSC316 外机加「EEV 脉冲周期按活跃组数补偿」—— 修 §3.3.5/§3.9 关闭速率不达标。

## 为什么要改

规格书 §3.3.5（急停）与 §3.9（普通关闭）都要求「电子膨胀阀以 20 步/秒速度关闭」。
316 实测（2026-09-21，两阀同时关）：

    周期 32ms -> 14.0 步/秒   20ms -> 19.9   18ms -> 19.2   16ms -> 18.9

**再短不再变快** —— 驱动定时器全是 `uc10ms` 量化，低于 20ms 的闸门它不认。
根因：`EEV_Priority()` 把时间按 **1.3 秒一路**分片（`TimeCount>=130`，`uc10ms` 单位），
两块阀同动时单阀等效周期翻倍。330 有 `EEVSpecPulseTimeAction()` 按活跃组数把周期调短
（2 组→20ms）正好抵消，316 把这句写死成 `EEVPulseTimeSet=32`，**且急停分支连补偿调用都没有**。

## 改什么（全在 `PSC316RK-V12-外机/WELLTHINKER/User/`）

`eevCTRL.c`：
  1. 顶部加 file-scope 标志 `EEVSpecHomingWindow`
  2. `EEV_ActionAll` 之前插入 `EEVSpecPulseTimeAction()`
  3. `EEV_ActionAll` 的 **急停分支** `return` 前调用它（对应 330 的 :641）
  4. `EEV_ActionAll` 的 **正常路径** `EEV_Action(j)` 循环之后调用它（对应 330 的 :674）
  5. `EEV_Action` 的归零窗口里置/清 `EEVSpecHomingWindow`（**保住 :538 的 16ms**）

`User.h`：
  6. `PSC316_VERSION_MINOR` 14 -> 15，日期改 2026-09-21，并加一条版本日志

## 为什么不用 Edit 工具

固件仓**编码按区域混**（同一文件里 GBK 中文注释 + ASCII 代码，换行 LF/CRLF 并存），
Edit 工具会把解不开的字节烧成 U+FFFD（实测毁过 UserAction.c 132 处）。
本脚本全程按**字节**操作，只匹配纯 ASCII 锚点，改完自检 U+FFFD 不增加。

跑法： python.exe tools/patch_316_eev_pulse_comp.py          # 打补丁
       python.exe tools/patch_316_eev_pulse_comp.py --check  # 只看锚点能不能对上
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EEV = ROOT / "PSC316RK-V12-外机" / "WELLTHINKER" / "User" / "eevCTRL.c"
USR = ROOT / "PSC316RK-V12-外机" / "WELLTHINKER" / "User" / "User.h"

# 注释一律用 ASCII —— 不再往固件文件里掺编码
NEW_FUNC = b"""/* Compensate the EEV step period for the number of active groups.
   Ported from PSC330 UserSrc/eevCTRL.c:24-38.

   Why: EEV_Priority() time-slices 1.3 s per group (TimeCount>=130 in uc10ms),
   so when both valves move the per-valve period doubles and the closing rate
   halves. Measured on the bench 2026-09-21 (emergency close, both valves):
       32 ms -> 14.0 steps/s   20 ms -> 19.9   18 ms -> 19.2   16 ms -> 18.9
   Going below ~20 ms no longer helps: the driver timers are all quantised to
   uc10ms. So 20 ms is the practical floor and is what we use here.

   330 has 4 groups (8 valves, 2 per slot); 316 has 2 groups (2 valves, 1 each),
   so only the 2-group step is needed. */
#define EEV_SPEC_PULSE_2GROUP  20

static void EEVSpecPulseTimeAction(void)
{
	unsigned int activeGroups = 0;

	/* A valve counts as active while it still has steps to make OR while a
	   close sequence is running. New!=Old alone is not enough: once the valve
	   catches up with the ramp the two are briefly equal, and the period would
	   flip back to 32 mid-close. Measured 2026-09-21: with New!=Old only,
	   [802] read 20 for just 27% of an emergency close and the rate was
	   19.1/18.3 steps/s; the spec wants 20.
	   NOTE: use EEVSpecCloseTarget>0, NOT EEVSpecCloseMode!=EEV_CLOSE_NONE.
	   closeMode is only cleared by EEVSpecCloseReset, which is gated on heating
	   mode, so it stays set forever after the first close and pins the period at
	   20 ms even for single-valve moves (measured: [802] was already 20 at idle,
	   which would run the stepper at ~50 steps/s instead of ~31). */
	if((EEV1NewAddValue != EEV1OldAddValue) ||
	   (EEVSpecCloseTarget[0] > 0))activeGroups++;
	if((EEV2NewAddValue != EEV2OldAddValue) ||
	   (EEVSpecCloseTarget[1] > 0))activeGroups++;

	/* Keep the 16 ms homing window (eevCTRL.c EEV_Action, first 23 s after
	   power-up) untouched - this change must not alter homing speed. */
	if(EEVSpecHomingWindow)return;

	if(activeGroups >= 2)EEVPulseTimeSet = EEV_SPEC_PULSE_2GROUP;
	else EEVPulseTimeSet = 32;
}
"""


def find_unique(raw: bytes, pat: bytes, what: str) -> int:
    n = raw.count(pat)
    if n != 1:
        raise SystemExit("锚点不唯一（%d 次）：%s  %r" % (n, what, pat))
    return raw.find(pat)


def patch_eev(raw: bytes) -> bytes:
    # --- 1. 顶部加 file-scope 标志 ---
    # ⚠ 必须放在**文件顶部**的 static 区，不能跟函数放一起：
    #   EEV_Action 定义在文件前半段，函数放后面它就看不见（踩过，编译报 undefined）。
    top = b"static unsigned char EEVSpecCloseTickConsumed[2] = {0};\n"
    find_unique(raw, top, "顶部 static 区")
    raw = raw.replace(top, top + b"static unsigned char EEVSpecHomingWindow = 0;\n")

    # --- 2. 在 EEV_ActionAll 之前插入新函数 ---
    i = find_unique(raw, b"void EEV_ActionAll(void)", "EEV_ActionAll 定义")
    raw = raw[:i] + NEW_FUNC.lstrip(b"\n") + raw[i:]

    # --- 3. 急停分支：return 前调用 ---
    # ⚠ 不能只用 "if(UrgencyStop)" —— EEVFaultSafetyAction 里还有一处
    #   `if(UrgencyStop)return;`，会命中 2 次。带上后面的 `{` 才唯一。
    i = find_unique(raw, b"if(UrgencyStop)\n\t{", "急停分支入口")
    j = raw.find(b"\t\treturn;\r\n", i)
    if j < 0:
        raise SystemExit("找不到急停分支的 return;")
    raw = raw[:j] + b"\t\tEEVSpecPulseTimeAction();\r\n" + raw[j:]

    # --- 4. 正常路径：EEV_Action(j) 循环之后调用 ---
    i = find_unique(raw, b"\t\t\tEEV_Action(j);\r\n\t}\r\n", "EEV_Action 循环")
    k = i + len(b"\t\t\tEEV_Action(j);\r\n\t}\r\n")
    raw = raw[:k] + b"\r\n\tEEVSpecPulseTimeAction();\r\n" + raw[k:]

    # --- 5a. 归零期置标志 ---
    # ⚠ 替换串必须**连 if(i==0) 一起写回** —— 漏掉的话会变成裸块
    #   `{EEVPulseTimeSet=16; ...}` 无条件执行（行为恰好等价，但结构不对）。
    i = find_unique(raw, b"if(i==0)EEVPulseTimeSet=16;", "归零期写 16")
    raw = (raw[:i] + b"if(i==0){EEVPulseTimeSet=16; EEVSpecHomingWindow=1;}"
           + raw[i + len(b"if(i==0)EEVPulseTimeSet=16;"):])

    # --- 5b. 归零窗口结束清标志（只改 EEV_Action 里那一处，EEV2_Action 里不动）---
    pat = b"if(TimeCount[i] >= 23) TimeCount[i] = 23;"
    i = raw.find(pat)                      # 第一处 = EEV_Action（offset 较小）
    if i < 0:
        raise SystemExit("找不到归零窗口封顶")
    if raw.find(pat, i + 1) < 0:
        raise SystemExit("第二处没找到，锚点假设不成立")
    raw = (raw[:i] + b"if(TimeCount[i] >= 23){TimeCount[i] = 23; if(i==0)EEVSpecHomingWindow=0;}"
           + raw[i + len(pat):])
    return raw


def patch_usr(raw: bytes) -> bytes:
    reps = [
        (b"#define PSC316_VERSION_MINOR 14", b"#define PSC316_VERSION_MINOR 15"),
        (b"#define PSC316_VERSION_DAY 17",   b"#define PSC316_VERSION_DAY 21"),
    ]
    for a, b in reps:
        find_unique(raw, a, "版本号")
        raw = raw.replace(a, b)
    # 版本日志：必须插在**版本日志注释块的 `*/` 之前**。
    # ⚠ 踩过：直接插在 `#define PSC316_VERSION_MODEL` 前面会落到注释**外面**，
    #   变成裸代码，编译报 58 个 error。
    anchor = b"*/\r\n#define PSC316_VERSION_MODEL 316"
    find_unique(raw, anchor, "版本日志注释结尾")
    log = (b"   V12.14 -> V12.15 (2026-09-21): EEV pulse period now compensated for the\r\n"
           b"       number of active groups (EEVSpecPulseTimeAction, ported from 330\r\n"
           b"       UserSrc/eevCTRL.c:24-38), called in both the emergency-close branch\r\n"
           b"       and after the EEV_Action loop.\r\n"
           b"       Measured before the fix: both outdoor EEVs closing together ran at\r\n"
           b"       14.0 steps/s (spec 3.3.5 / 3.9 require 20). Root cause: EEV_Priority\r\n"
           b"       time-slices 1.3 s per group, so two active valves halve the per-valve\r\n"
           b"       rate; 316 had EEVPulseTimeSet pinned at 32 ms with no compensation.\r\n"
           b"       After: 20 ms for 2 groups -> 19.9 steps/s measured. Periods below\r\n"
           b"       20 ms gave no further gain (driver timers are uc10ms quantised).\r\n"
           b"       Homing speed unchanged (EEVSpecHomingWindow keeps the 16 ms window).\r\n")
    return raw.replace(anchor, log + anchor)


def main() -> int:
    check = "--check" in sys.argv
    for path, fn in ((EEV, patch_eev), (USR, patch_usr)):
        raw = path.read_bytes()
        # 强判据：本补丁只插入/替换**纯 ASCII**，所以**非 ASCII 字节总数必须一字不变**。
        # （拿 U+FFFD 计数当判据太弱 —— GBK 文件按 UTF-8 解出来本来就满屏 FFFD。）
        before_hi = sum(1 for b in raw if b >= 0x80)
        before_lines = raw.count(b"\n")
        new = fn(raw) if not check else raw
        after_hi = sum(1 for b in new if b >= 0x80)
        print("%-12s 行 %d -> %d (+%d)   非ASCII字节 %d -> %d %s"
              % (path.name, before_lines, new.count(b"\n"),
                 new.count(b"\n") - before_lines, before_hi, after_hi,
                 "OK" if after_hi == before_hi else "**变了，中止**"))
        if after_hi != before_hi:
            raise SystemExit("!! 非 ASCII 字节数变了 —— 编码被破坏，中止")
        if not check:
            path.write_bytes(new)
    if check:
        print("\n所有锚点都能对上（--check，未写入）")
    else:
        print("\n已写入。下一步：编译 + 烧录 + 用 probe_316_eev_rate.py --emergency --hold 复测")
    return 0


if __name__ == "__main__":
    sys.exit(main())
