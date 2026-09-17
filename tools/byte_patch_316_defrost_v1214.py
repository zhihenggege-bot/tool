"""V12.14：化霜三处按规格书 4.4 修正。

规格书原文（用户 2026-09-17 提供的完整条款）：
  item1-2  化霜开始条件②「环境温度低于**10度**保持60秒以上」
  item1    7 个条件里只有 ④⑤ 标了「（环境温度定时化霜**除外**）」，②没有除外
  正文     「环温低于**【环境温度定时化霜温度设定值】**，满足化霜时间间隔化霜一次，
            环温低于4度，每次化霜时间为【环境温度定时化霜时间】，
            环温高于6度每次化霜时间为【环境温度定时化霜时间】-1分钟」

三处改动：
  A. 正常化霜的环温阈值 = **字面 10.0C**（原来跟着参数 DefrostEnvTempSet 走）
     定时化霜的阈值仍用【环境温度定时化霜温度设定值】（这部分原来就是对的）
  B. 定时化霜的「环温低保持」30 秒 -> **60 秒**（item1-2 没有给它除外）
  C. 定时化霜时间分界：单点 4.0 -> **4.0/6.0 双点回差**（4~6 之间保持上次判定）

文件编码（已实测）：
  DefAction.c = UTF-8 + **LF**
  User.h      = UTF-8 + **CRLF**
写法沿用既有脚本：字节级替换 + 写回后回读校验编码/换行。

跑法：
    python.exe tools/byte_patch_316_defrost_v1214.py            # 试运行
    python.exe tools/byte_patch_316_defrost_v1214.py --apply    # 写入
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
    has_crlf = b"\r\n" in raw
    nl = "\r\n" if has_crlf else "\n"

    print(f"--- {rel}  (enc={enc}, nl={'CRLF' if has_crlf else 'LF'}) ---")
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
        print(f"    ok  [{tag}]")

    if out == raw:
        print("    （无变化）")
        return
    if APPLY:
        path.write_bytes(out)
        chk = path.read_bytes()
        assert detect_encoding(chk) == enc, "写回后编码变了！"
        assert (b"\r\n" in chk) == has_crlf, "写回后换行风格变了！"
        print("    已写入并校验编码/换行")
    else:
        print("    （试运行，未写入）")


PATCHES: list[tuple[str, list[tuple[str, str, str]], str]] = [
    (
        "User/DefAction.c",
        [
            # ---- A 的常量定义 ----
            (
                "A: 加字面 10.0C 常量",
                "static unsigned char PSC316FinSensorErr(unsigned int SysNo)\n",
                "/* 20260917 V12.14: 规格书 4.4 item1-2「环境温度低于10度保持60秒以上」——\n"
                "   这处是**字面固定 10.0C**，不是【环境温度定时化霜温度设定值】。\n"
                "   只有定时化霜模式的阈值才用那个参数（规格书正文：「环温低于\n"
                "   【环境温度定时化霜温度设定值】」）。EnviTempAI0Disp 单位 0.1C，10 度 = 100。 */\n"
                "#define DEFROST_NORMAL_ENV_MAX   100\n"
                "\n"
                "static unsigned char PSC316FinSensorErr(unsigned int SysNo)\n",
            ),
            # ---- C 定时化霜时间：单点 4.0 -> 4/6 回差 ----
            (
                "C: 4.0/6.0 双点回差",
                "static unsigned int PSC316TimedDefrostSeconds(void)\n"
                "{\n"
                "\tif((EnviTempAI0Disp > 40)&&(DefrostEnvTimeSet > 1)) return (DefrostEnvTimeSet-1)*60;  /* spec 20260428: use 4C boundary */\n"
                "\treturn DefrostEnvTimeSet*60;\n"
                "}\n",
                "static unsigned int PSC316TimedDefrostSeconds(void)\n"
                "{\n"
                "\t/* 20260917 V12.14: 规格书正文给的是**两个点** ——\n"
                "\t     环温低于 4 度 -> 用【环境温度定时化霜时间】\n"
                "\t     环温高于 6 度 -> 用【环境温度定时化霜时间】- 1 分钟\n"
                "\t   4.0~6.0 之间规格书没规定，按回差带处理 —— 保持上一次的判定。\n"
                "\t   原实现是单点 (EnviTempAI0Disp > 40)，4~6 之间直接按\"-1 分钟\"给，\n"
                "\t   与规格书的两个点不符。\n"
                "\t   EnviTempAI0Disp 单位 0.1C：4.0C = 40，6.0C = 60。 */\n"
                "\tstatic unsigned char EnvHighBand = 0;\t/* 0=满时间  1=-1分钟 */\n"
                "\tif(EnviTempAI0Disp <= 40) EnvHighBand = 0;\n"
                "\telse if(EnviTempAI0Disp >= 60) EnvHighBand = 1;\n"
                "\tif(EnvHighBand && (DefrostEnvTimeSet > 1)) return (DefrostEnvTimeSet-1)*60;\n"
                "\treturn DefrostEnvTimeSet*60;\n"
                "}\n",
            ),
            # ---- A+B 环温阈值分模式 + 保持时间 30->60 ----
            (
                "A+B: 阈值分模式、定时保持改 60 秒",
                "\tUnitTimedDefrostMode = PSC316UnitTimedDefrostMode();\n"
                "\tif((UserWorkModeSet==1)&&(EnviTempAI0Disp < DefrostEnvTempSet))\n"
                "\t{\n"
                "\t\tif(UnitTimedDefrostMode)\n"
                "\t\t{\n"
                "\t\t\tNormalEnvLowCount = 0;\n"
                "\t\t\tTimedEnvLowCount += uc1s;\n"
                "\t\t\tif(TimedEnvLowCount >= 30) TimedEnvLowCount = 30;\n"
                "\t\t}\n"
                "\t\telse\n"
                "\t\t{\n"
                "\t\t\tTimedEnvLowCount = 0;\n"
                "\t\t\tNormalEnvLowCount += uc1s;\n"
                "\t\t\tif(NormalEnvLowCount >= 60) NormalEnvLowCount = 60;\n"
                "\t\t}\n"
                "\t}\n"
                "\telse\n"
                "\t{\n"
                "\t\tNormalEnvLowCount = 0;\n"
                "\t\tTimedEnvLowCount = 0;\n"
                "\t}\n",
                "\tUnitTimedDefrostMode = PSC316UnitTimedDefrostMode();\n"
                "\t/* 20260917 V12.14: 两种模式的环温阈值不同 ——\n"
                "\t   定时化霜用【环境温度定时化霜温度设定值】(DefrostEnvTempSet)，\n"
                "\t   正常化霜用规格书 item1-2 的**字面 10.0C**(DEFROST_NORMAL_ENV_MAX)。\n"
                "\t   原来两种模式共用 DefrostEnvTempSet 一道门，正常模式的阈值会跟着参数跑偏。\n"
                "\t   同时把定时模式的\"环温低保持\"从 30 秒改成 60 秒：规格书 item1 的 7 个\n"
                "\t   条件里只有 ④⑤ 标了「环境温度定时化霜除外」，item1-2 的「保持60秒以上」\n"
                "\t   没有除外，定时模式同样要 60 秒。 */\n"
                "\tif(UserWorkModeSet==1)\n"
                "\t{\n"
                "\t\tif(UnitTimedDefrostMode)\n"
                "\t\t{\n"
                "\t\t\tNormalEnvLowCount = 0;\n"
                "\t\t\tif(EnviTempAI0Disp < DefrostEnvTempSet)\n"
                "\t\t\t{\n"
                "\t\t\t\tTimedEnvLowCount += uc1s;\n"
                "\t\t\t\tif(TimedEnvLowCount >= 60) TimedEnvLowCount = 60;\n"
                "\t\t\t}\n"
                "\t\t\telse TimedEnvLowCount = 0;\n"
                "\t\t}\n"
                "\t\telse\n"
                "\t\t{\n"
                "\t\t\tTimedEnvLowCount = 0;\n"
                "\t\t\tif(EnviTempAI0Disp < DEFROST_NORMAL_ENV_MAX)\n"
                "\t\t\t{\n"
                "\t\t\t\tNormalEnvLowCount += uc1s;\n"
                "\t\t\t\tif(NormalEnvLowCount >= 60) NormalEnvLowCount = 60;\n"
                "\t\t\t}\n"
                "\t\t\telse NormalEnvLowCount = 0;\n"
                "\t\t}\n"
                "\t}\n"
                "\telse\n"
                "\t{\n"
                "\t\tNormalEnvLowCount = 0;\n"
                "\t\tTimedEnvLowCount = 0;\n"
                "\t}\n",
            ),
            # ---- B 起判条件里的 30 -> 60 ----
            (
                "B: 起判条件 TimedEnvLowCount>=30 -> >=60",
                "\t\t\t&&((TimerDefrostMode[i] && (TimedEnvLowCount>=30))\n",
                "\t\t\t&&((TimerDefrostMode[i] && (TimedEnvLowCount>=60))\n",
            ),
        ],
        "A 阈值分模式 / B 定时保持 30->60s / C 4.0->4.0+6.0 回差",
    ),
    (
        "User/User.h",
        [
            (
                "版本号",
                "#define PSC316_VERSION_MINOR 13\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
                "#define PSC316_VERSION_MINOR 14\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
            ),
            (
                "版本历史",
                "\n */\n#define PSC316_VERSION_MODEL 316\n",
                "\n"
                "   V12.13 -> V12.14 (2026-09-17)：化霜三处按规格书 4.4 修正。\n"
                "       用户提供了 4.4 的完整条款（item1 化霜开始 7 条件 / item2 结束 3 原因 /\n"
                "       item3 开始动作 / item4 结束动作），逐条核对后发现：\n"
                "         A. 正常化霜的环温阈值应是规格书 item1-2 的**字面 10.0C**，\n"
                "            而代码两种模式共用【环境温度定时化霜温度设定值】——正常模式\n"
                "            的阈值会跟着参数跑偏。改成：定时模式用参数（本来就对），\n"
                "            正常模式用字面 10.0C（新常量 DEFROST_NORMAL_ENV_MAX = 100）。\n"
                "         B. 定时化霜的\"环温低保持\"是 30 秒，但规格书 item1 的 7 个条件里\n"
                "            只有 ④⑤ 标了「环境温度定时化霜除外」，item1-2 的「保持60秒以上」\n"
                "            没有除外 -> 定时模式同样要 60 秒。改成 60。\n"
                "         C. 定时化霜时间的环温分界：规格书给的是**两个点**\n"
                "            （低于4度用满时间、高于6度用 -1 分钟），原实现是单点\n"
                "            (EnviTempAI0Disp > 40)，4~6 之间直接按 -1 分钟给。\n"
                "            改成 4.0/6.0 双点回差，中间保持上次判定。\n"
                "       核对中确认**符合**、未改动的：item1-3/4/5/6/7、item2 三条结束原因\n"
                "       （含\"高压开关跳开且此时高压不报警\"）、item3 全部动作（屏蔽低压开关、\n"
                "       风机关、四通阀失电、未开压机间隔30秒开）、item4（全关+延时60秒+发结束指令）。\n"
                "       影响面：只影响化霜判据；制冷/制热/风机路径未动。\n"
                " */\n#define PSC316_VERSION_MODEL 316\n",
            ),
        ],
        "版本号 V12.13 -> V12.14，并补版本历史",
    ),
]


def main() -> int:
    print("=" * 74)
    print("V12.14 化霜三处按规格书 4.4 修正" + ("   [APPLY]" if APPLY else "   [试运行]"))
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
