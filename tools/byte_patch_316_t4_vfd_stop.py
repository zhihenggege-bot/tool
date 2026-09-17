"""V12.13：类型4（变频+定速）恢复「变频风机关」。

规格书流程图《双风机室外机时（一定一变）的逻辑框图》最上面那一支写得明确：

    变频风机减频 -> 变频风机在最低频? --是--> 【变频风机关】
                                      --否--> 【变频风机减频】

V12.10 按用户当时的口头指示「所在的外机有压缩机运行就不能停机」，把类型2 和类型4
两处的停机分支一起删了（当时专门问过"类型4 要不要跟着变"，用户答"要"）。
现在流程图显示：**类型4 在最低频且仍在降档时应该关掉变频风机**。

用户裁定 (a)：只对类型2 保留"不停机"，类型4 恢复停机。理由：
  * 类型2 只有一台变频风机，关了就没风机了 -> 不能停
  * 类型4 有定频风机兜底，关变频只是"降到下一档" -> 可以停

改法：类型4 的 else（定频已关）分支，在"变频已到最低频"时恢复停机，
并保留最短运行时间 + 换挡间隔两道门。

编码：UserAction.c / User.h = UTF-8 + CRLF、无 BOM。字节级替换，写回后回读校验。

跑法：
    python.exe tools/byte_patch_316_t4_vfd_stop.py            # 试运行
    python.exe tools/byte_patch_316_t4_vfd_stop.py --apply    # 写入
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
        print(f"    ok  [{tag}] {old_s.strip().splitlines()[0][:60]}")

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
                "类型4 恢复变频风机关机",
                "\t\t\telse\n"
                "\t\t\t{\n"
                "\t\t\t\t/* 20260917 V12.10: 同上 —— 变频风机减到最低频为止，不停机。\n"
                "\t\t\t\t   类型4 里定速风机的起停仍按原分段逻辑，未动。 */\n"
                "\t\t\t\tif(OutdoorVfdOn && (OutdoorVfdSpeed > MinSpeed))\n"
                "\t\t\t\t{\n"
                "\t\t\t\t\tif(uc1s) OutdoorVfdSpeed -= Step;\n"
                "\t\t\t\t}\n"
                "\t\t\t}\n",
                "\t\t\telse\n"
                "\t\t\t{\n"
                "\t\t\t\t/* 20260917 V12.13: 类型4 恢复「变频风机关」——\n"
                "\t\t\t\t   规格书流程图《双风机室外机时（一定一变）》最上面那一支：\n"
                "\t\t\t\t     变频风机减频 -> 变频风机在最低频? --是--> 变频风机关\n"
                "\t\t\t\t   类型4 有定频风机兜底，关变频只是降到下一档，不会没风机；\n"
                "\t\t\t\t   类型2 只有一台变频风机（关了就没风机），那边保留不停机。 */\n"
                "\t\t\t\tif(OutdoorVfdOn && (OutdoorVfdSpeed > MinSpeed))\n"
                "\t\t\t\t{\n"
                "\t\t\t\t\tif(uc1s) OutdoorVfdSpeed -= Step;\n"
                "\t\t\t\t}\n"
                "\t\t\t\telse if(OutdoorVfdOn\n"
                "\t\t\t\t\t&& (OutdoorFanRunSeconds[0] >= FanMinRunTimeSet)\n"
                "\t\t\t\t\t&& (OutdoorFanChangeSeconds >= 15))\n"
                "\t\t\t\t{\n"
                "\t\t\t\t\tOutdoorVfdOn = 0;\n"
                "\t\t\t\t\tOutdoorVfdSpeed = 0;\n"
                "\t\t\t\t\tOutdoorFanChangeSeconds = 0;\n"
                "\t\t\t\t}\n"
                "\t\t\t}\n",
            ),
        ],
        "类型4：变频到最低频且仍在降档 -> 关机（保留最短运行+换挡门）",
    ),
    (
        "User/User.h",
        [
            (
                "版本号",
                "#define PSC316_VERSION_MINOR 12\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
                "#define PSC316_VERSION_MINOR 13\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
            ),
            (
                "版本历史",
                "\n */\n#define PSC316_VERSION_MODEL 316\n",
                "\n"
                "   V12.12 -> V12.13 (2026-09-17)：类型4（变频+定速）恢复「变频风机关」。\n"
                "       规格书流程图《双风机室外机时（一定一变）的逻辑框图》最上面那一支：\n"
                "           变频风机减频 -> 变频风机在最低频? --是--> 变频风机关\n"
                "                                             --否--> 变频风机减频\n"
                "       V12.10 按当时的口头指示「有压缩机运行就不能停机」，把类型2 与类型4\n"
                "       两处的停机分支一起删了。现在按流程图分开处理：\n"
                "         * 类型2 只有一台变频风机，关了就没风机 -> 保留「减到最低频为止」\n"
                "         * 类型4 有定频风机兜底，关变频只是降到下一档 -> 恢复停机\n"
                "       改法：类型4 的 else（定频已关）分支恢复\n"
                "         `else if(OutdoorVfdOn && RunSeconds[0] >= FanMinRunTimeSet\n"
                "                  && OutdoorFanChangeSeconds >= 15) { OutdoorVfdOn = 0; ... }`\n"
                "       此时定频也是关的，所以关变频后两台全关。\n"
                "       影响面：只影响风机类型4；类型2 未动。\n"
                " */\n#define PSC316_VERSION_MODEL 316\n",
            ),
        ],
        "版本号 V12.12 -> V12.13，并补版本历史",
    ),
]


def main() -> int:
    print("=" * 74)
    print("V12.13 类型4 恢复「变频风机关」" + ("   [APPLY]" if APPLY else "   [试运行]"))
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
