"""V12.9：修「机型0 + 风机类型0（单风机双速）」低速输出接错端子。

IO 点位表定义：
    Y02 = 风机1 / 定速风机 / 变频风机使能
    Y03 = 风机2 / 低速 / 辅助定速风机
    Y07 = 双速风机高速接触器

而 ErrorCheck.c 的 case 0 把「低速」写到了 Fan1Y03(=Y02)，并且 UserAction.c 的
类型0 互锁块无条件把 Y03 清零 —— 结果类型0 的低速端子 Y03 永远没输出，
Y02（定速风机端子）被当成了双速风机的低速端子。

三处一起改：
    1. ErrorCheck.c   case 0 输出分发：低速 Fan1Y03 -> Fan3Y07
    2. UserAction.c   类型0 互锁块：无条件清 Y03 -> Y03/Y07 互斥
    3. modbus.c       类型0 清 HandDebugY02 —— 改完 Y02 才是"类型0 用不到的端子"，
                      原来的写法在新语义下正好正确，**不需要改**（脚本只做校验）

⚠ 这个仓库同一份代码里编码是混的：
    ErrorCheck.c = GBK ；UserAction.c / User.h = UTF-8（都是 CRLF、无 BOM）
   本脚本一律按 **字节** 替换，中文按目标文件的实际编码编码后再写入。

跑法：
    python.exe tools/byte_patch_316_type0_fan_pin.py            # 试运行（只看结果）
    python.exe tools/byte_patch_316_type0_fan_pin.py --apply    # 真正写入
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


def patch(rel: str, pairs: list[tuple[str, str]], note: str) -> None:
    """在 rel 指向的文件里做字节级替换。pairs 里的字符串用 \\n 表示换行，按文件实际换行改造。"""
    global problems
    path = SRC / rel
    raw = path.read_bytes()
    enc = detect_encoding(raw)
    nl = "\r\n" if b"\r\n" in raw else "\n"

    print(f"--- {rel}  (enc={enc}, nl={'CRLF' if nl == chr(13)+chr(10) else 'LF'}) ---")
    print(f"    {note}")
    out = raw
    for old_s, new_s in pairs:
        old = old_s.replace("\n", nl).encode(enc)
        new = new_s.replace("\n", nl).encode(enc)
        n = out.count(old)
        if n != 1:
            print(f"    !! 匹配 {n} 次（应为 1），跳过：{old_s[:60]!r}")
            problems += 1
            continue
        out = out.replace(old, new, 1)
        print(f"    ok  {old_s.strip()[:64]}")
        print(f"     -> {new_s.strip().splitlines()[0][:64]}")

    if out == raw:
        print("    （无变化）")
        return
    if APPLY:
        path.write_bytes(out)
        # 写回后立刻回读校验编码与换行
        chk = path.read_bytes()
        assert detect_encoding(chk) == enc, "写回后编码变了！"
        assert (b"\r\n" in chk) == (nl == "\r\n"), "写回后换行变了！"
        print("    已写入并校验编码/换行")
    else:
        print("    （试运行，未写入）")


PATCHES: list[tuple[str, list[tuple[str, str]], str]] = [
    (
        "User/ErrorCheck.c",
        [
            (
                "\t\t\t\tcase 0: /* one two-speed fan: Y03 low, Y04 high */",
                "\t\t\t\tcase 0: /* one two-speed fan: Y03 low, Y07 high */",
            ),
            (
                "\t\t\t\t\tif(FanOpenSet2) { Fan1Y03 = 0; Fan2HighY04 = 1; }",
                "\t\t\t\t\tif(FanOpenSet2) { Fan3Y07 = 0; Fan2HighY04 = 1; }",
            ),
            (
                "\t\t\t\t\telse { Fan1Y03 = FanOpenSet; Fan2HighY04 = 0; }",
                "\t\t\t\t\telse { Fan3Y07 = FanOpenSet; Fan2HighY04 = 0; }",
            ),
        ],
        "case 0 低速输出 Y02(Fan1Y03) -> Y03(Fan3Y07)；注释里的旧引脚 Y04 同步改成 Y07",
    ),
    (
        "User/UserAction.c",
        [
            (
                "\tif(OutdoorFanTypeSet == 0)\n"
                "\t{\n"
                "\t\tFan3Y07 = 0;\n"
                "\t\tHandDebugY03 = 0;\n"
                "\t\tif(Fan2HighY04) Fan1Y03 = 0;\n"
                "\t\tif(HandDebugY07) HandDebugY02 = 0;\n"
                "\t}\n",
                "\tif(OutdoorFanTypeSet == 0)\n"
                "\t{\n"
                "\t\t/* 20260917 V12.9: 单风机双速的低速在 Y03、高速在 Y07（不是 Y02）。\n"
                "\t\t   这里只能做「Y03/Y07 互斥」，不能像以前那样无条件把 Y03 清零 ——\n"
                "\t\t   那会把低速输出直接打死。Y02 在类型0 用不到，手动位一并禁掉。 */\n"
                "\t\tHandDebugY02 = 0;\n"
                "\t\tif(Fan2HighY04) Fan3Y07 = 0;\n"
                "\t\tif(HandDebugY07) HandDebugY03 = 0;\n"
                "\t}\n",
            ),
        ],
        "类型0 互锁块：不再无条件清 Y03，改成 Y03/Y07 互斥",
    ),
    (
        "User/User.h",
        [
            (
                "#define PSC316_VERSION_MINOR 8\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
                "#define PSC316_VERSION_MINOR 9\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
            ),
            (
                "\n */\n#define PSC316_VERSION_MODEL 316\n",
                "\n"
                "   V12.8 -> V12.9 (2026-09-17)：修「机型0 + 风机类型0（单风机双速）"
                "低速输出接错端子」。\n"
                "       点位表定义 Y02=风机1/定速风机/变频使能、Y03=风机2/低速/辅助定速、\n"
                "       Y07=双速风机高速接触器。ErrorCheck.c 的 case 0 却把「低速」写到\n"
                "       Fan1Y03(=Y02)，UserAction.c 的类型0 互锁块又无条件把 Y03 清零 ——\n"
                "       结果类型0 的低速端子 Y03 一直没有输出，Y02（定速风机端子）被当成\n"
                "       了双速风机的低速。case 0 自己的注释本来就写着「Y03 low」，是宏名与\n"
                "       实际引脚脱节之后没跟着改。\n"
                "       改法：case 0 低速改驱动 Fan3Y07(=Y03)；类型0 互锁块改成 Y03/Y07 互斥。\n"
                "       影响面：只影响风机类型0；类型1/2/3/4 的映射本来就与点位表一致，未动。\n"
                " */\n#define PSC316_VERSION_MODEL 316\n",
            ),
        ],
        "版本号 V12.8 -> V12.9，并补版本历史",
    ),
]


def check_modbus() -> None:
    """第 3 处只做校验：modbus.c 类型0 清 HandDebugY02，在新语义下是对的。"""
    path = SRC / "modbus" / "modbus.c"
    raw = path.read_bytes()
    enc = detect_encoding(raw)
    nl = "\r\n" if b"\r\n" in raw else "\n"
    want = (
        "\tif(OutdoorFanTypeSet == 0)\n\t{\n\t\tHandDebugY02 = 0;\n\t}\n"
    ).replace("\n", nl).encode(enc)
    print("--- modbus/modbus.c  (只校验，不改) ---")
    if raw.count(want) == 1:
        print("    ok  类型0 清的是 HandDebugY02 —— 改完后 Y02 正是类型0 用不到的端子，")
        print("        原来的写法在新语义下恰好正确，无需修改。")
    else:
        global problems
        print("    !! 没找到预期片段，请人工确认")
        problems += 1


def main() -> int:
    print("=" * 74)
    print("V12.9 类型0 风机低速端子 Y02 -> Y03" + ("   [APPLY]" if APPLY else "   [试运行]"))
    print("=" * 74)
    for rel, pairs, note in PATCHES:
        patch(rel, pairs, note)
    check_modbus()
    print()
    print("=" * 74)
    if problems:
        print(f"有 {problems} 处问题，未完成的项见上。")
        return 1
    print("全部替换成功。" + ("已写入。" if APPLY else "（试运行，加 --apply 才写入）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
