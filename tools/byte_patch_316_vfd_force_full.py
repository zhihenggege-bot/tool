"""V12.11：变频风机「没开且冷凝>45 → 满频」不再等 30 秒确认。

规格书：**若风机没开，冷凝温度大于45度满频。**

原来的代码要求冷凝 >45 持续 30 秒（OutdoorVfdForceFullCount 累到 30）才把
ForceFull 置 1，启动时才给 MaxSpeed。但启动条件里那一项是
`(!NeedUnload || ForceFull)`，而 NeedUnload = (冷凝 < 34)，冷凝 >45 时
`!NeedUnload` 已经为真 —— 所以风机第一条扫描就以 **MinSpeed** 起来了，
那个 30 秒计数从此再也轮不到用（风机一开，`!OutdoorVfdOn` 就为假，
启动块不再执行）。实测口径：启动给 20.0Hz，再靠 >36 的加载逻辑爬到 50.0Hz，
约 15 秒。与规格书的「满频」不符。

改法：启动时直接看冷凝温度 —— `OutdoorVfdSpeed = (MaxCondTemp > 450) ? MaxSpeed : MinSpeed;`
同时把启动条件里的 `|| ForceFull` 去掉（恒等于 `!NeedUnload`）。
OutdoorVfdForceFullCount 不再参与判断，保留下来只当"冷凝>45 已持续多少秒"的指示器。
ForceFull 这个局部变量整个删掉。

编码：UserAction.c / User.h = UTF-8 + CRLF、无 BOM。按字节替换，写回后回读校验。

跑法：
    python.exe tools/byte_patch_316_vfd_force_full.py            # 试运行
    python.exe tools/byte_patch_316_vfd_force_full.py --apply    # 写入
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "PSC316RK-V12-外机" / "WELLTHINKER"

APPLY = "--apply" in sys.argv
problems = 0


def detect_encoding(raw: bytes) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise RuntimeError("既不是 UTF-8 也不是 GBK（可能已被写坏）")


def patch(rel: str, pairs: list[tuple[str, str, str]], note: str) -> None:
    global problems
    path = SRC / rel
    raw = path.read_bytes()
    enc = detect_encoding(raw)
    nl = "\r\n" if b"\r\n" in raw else "\n"

    print(f"--- {rel}  (enc={enc}, nl={'CRLF' if nl == chr(13) + chr(10) else 'LF'}) ---")
    print(f"    {note}")
    out = raw
    for tag, old_s, new_s in pairs:
        old = old_s.replace("\n", nl).encode(enc)
        new = new_s.replace("\n", nl).encode(enc)
        n = out.count(old)
        if n != 1:
            print(f"    !! [{tag}] 匹配 {n} 次（应为 1），跳过")
            problems += 1
            continue
        out = out.replace(old, new, 1)
        print(f"    ok  [{tag}] {old_s.strip().splitlines()[0][:62]}")

    if out == raw:
        print("    （无变化）")
        return
    if APPLY:
        path.write_bytes(out)
        chk = path.read_bytes()
        assert detect_encoding(chk) == enc, "写回后编码变了！"
        assert (b"\r\n" in chk) == (nl == "\r\n"), "写回后换行变了！"
        print("    已写入并校验编码/换行")
    else:
        print("    （试运行，未写入）")


PATCHES: list[tuple[str, list[tuple[str, str, str]], str]] = [
    (
        "User/UserAction.c",
        [
            (
                "删掉 ForceFull 局部变量",
                "\tunsigned char NeedLoad;\n"
                "\tunsigned char NeedUnload;\n"
                "\tunsigned char ForceFull;\n",
                "\tunsigned char NeedLoad;\n"
                "\tunsigned char NeedUnload;\n",
            ),
            (
                "启动时直接按冷凝温度给频率",
                "\tif(MaxCondTemp > 450)\n"
                "\t{\n"
                "\t\tif(OutdoorVfdForceFullCount < 30) OutdoorVfdForceFullCount += uc1s;\n"
                "\t}\n"
                "\telse OutdoorVfdForceFullCount = 0;\n"
                "\tForceFull = (OutdoorVfdForceFullCount >= 30) ? 1 : 0;\n"
                "\n"
                "\t/* A running compressor must have at least the minimum VFD fan command.\n"
                "\t   An off fan starts at full speed only after condensation temperature\n"
                "\t   remains above 45C for the required 30-second hold time. */\n"
                "\tif(!OutdoorVfdOn\n"
                "\t\t&& (!NeedUnload || ForceFull)\n"
                "\t\t&& (OutdoorFanStopSeconds[0] >= FanMinStopTimeSet)\n"
                "\t\t&& (OutdoorFanChangeSeconds >= 15))\n"
                "\t{\n"
                "\t\tOutdoorVfdOn = 1;\n"
                "\t\tOutdoorVfdSpeed = ForceFull ? MaxSpeed : MinSpeed;\n"
                "\t\tOutdoorFanChangeSeconds = 0;\n"
                "\t}\n",
                "\t/* 20260917 V12.11: 规格书「若风机没开，冷凝温度大于45度满频」——\n"
                "\t   启动瞬间就按冷凝温度给频率，不再等 30 秒的 ForceFull 确认。\n"
                "\t   原写法里启动条件那项是 (!NeedUnload || ForceFull)，而\n"
                "\t   NeedUnload = (冷凝 < 34)，冷凝 >45 时 !NeedUnload 已为真 —— 风机\n"
                "\t   第一条扫描就以 MinSpeed 起来了，那 30 秒计数从此再也轮不到用。\n"
                "\t   OutdoorVfdForceFullCount 保留，只当「冷凝>45 已持续多少秒」的指示器。 */\n"
                "\tif(MaxCondTemp > 450)\n"
                "\t{\n"
                "\t\tif(OutdoorVfdForceFullCount < 30) OutdoorVfdForceFullCount += uc1s;\n"
                "\t}\n"
                "\telse OutdoorVfdForceFullCount = 0;\n"
                "\n"
                "\t/* A running compressor must have at least the minimum VFD fan command. */\n"
                "\tif(!OutdoorVfdOn\n"
                "\t\t&& !NeedUnload\n"
                "\t\t&& (OutdoorFanStopSeconds[0] >= FanMinStopTimeSet)\n"
                "\t\t&& (OutdoorFanChangeSeconds >= 15))\n"
                "\t{\n"
                "\t\tOutdoorVfdOn = 1;\n"
                "\t\tOutdoorVfdSpeed = (MaxCondTemp > 450) ? MaxSpeed : MinSpeed;\n"
                "\t\tOutdoorFanChangeSeconds = 0;\n"
                "\t}\n",
            ),
        ],
        "变频风机启动不再等 30 秒；删 ForceFull",
    ),
    (
        "User/User.h",
        [
            (
                "版本号",
                "#define PSC316_VERSION_MINOR 10\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
                "#define PSC316_VERSION_MINOR 11\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
            ),
            (
                "版本历史",
                "\n */\n#define PSC316_VERSION_MODEL 316\n",
                "\n"
                "   V12.10 -> V12.11 (2026-09-17)：变频风机「没开且冷凝>45 → 满频」不再等 30 秒。\n"
                "       规格书原文是「若风机没开，冷凝温度大于45度满频」，没有保持时间。\n"
                "       原代码要 ForceFullCount 累到 30 才给 MaxSpeed；但启动条件里那项是\n"
                "       `(!NeedUnload || ForceFull)`，NeedUnload = (冷凝 < 34)，冷凝 >45 时\n"
                "       `!NeedUnload` 已为真 —— 风机第一条扫描就以 MinSpeed 起来了，\n"
                "       那 30 秒计数从此再也轮不到用（风机一开 !OutdoorVfdOn 就为假）。\n"
                "       实测口径是：启动给 20.0Hz，再靠 >36 的加载逻辑爬到 50.0Hz（约 15 秒），\n"
                "       与规格书的「满频」不符。\n"
                "       改法：`OutdoorVfdSpeed = (MaxCondTemp > 450) ? MaxSpeed : MinSpeed;`\n"
                "       启动条件里的 `|| ForceFull` 去掉（恒等于 !NeedUnload），ForceFull 局部变量删除；\n"
                "       OutdoorVfdForceFullCount 保留，只当「冷凝>45 已持续多少秒」的指示器。\n"
                "       影响面：只影响风机类型2 / 类型4 的变频风机启动瞬间。\n"
                " */\n#define PSC316_VERSION_MODEL 316\n",
            ),
        ],
        "版本号 V12.10 -> V12.11，并补版本历史",
    ),
]


def main() -> int:
    print("=" * 74)
    print("V12.11 变频风机：没开且冷凝>45 直接满频，不等 30 秒" + ("   [APPLY]" if APPLY else "   [试运行]"))
    print("=" * 74)
    for rel, pairs, note in PATCHES:
        patch(rel, pairs, note)
    print()
    print("=" * 74)
    if problems:
        print(f"有 {problems} 处未完成，见上。")
        return 1
    print("全部替换成功。" + ("已写入。" if APPLY else "（试运行，加 --apply 才写入）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
