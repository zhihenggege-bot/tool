"""V12.10：变频风机（风机类型2 单风机变频 / 类型4 变频+定速）

改两条，都是用户 2026-09-17 拍板的：

A. 「减到低频为止、不停机」—— 所在外机只要有压缩机在运行，变频风机就不许停机。
   OutdoorFanTypeIII() 只在有压机运行时被调用，所以把两处 `OutdoorVfdOn = 0`
   的停机分支删掉，减载减到【变频轴流风机最低频】为止，由函数末尾的
   `if(OutdoorVfdOn && (OutdoorVfdSpeed < MinSpeed)) OutdoorVfdSpeed = MinSpeed;`
   兜住。

B. 「变频风机加减载是动态的，没有保持 30 秒这一说」——
   原来要 OutdoorVfdLoadCount/UnloadCount 累到 30 才 NeedLoad/NeedUnload，
   等于每次加减载前先干等 30 秒。改成直接按冷凝温度判：
   冷凝 >36.0 每秒加、<34.0 每秒减、34~36 之间保持（这个带就是规格书给的迟滞）。
   两个计数变量保留，改成 0/1 表示当前处于 加载/减载/保持 哪一态，方便调试口看。

   ⚠ 未动的是「若风机没开、冷凝 >45 度满频」那条里的 30 秒确认（ForceFull）——
     用户只说了加减载。这条留待确认。

⚠ 编码：UserAction.c / User.h 都是 UTF-8 + CRLF、无 BOM。本脚本按字节替换，
   中文按 UTF-8 编码后写入，并在写回后回读校验编码与换行。

跑法：
    python.exe tools/byte_patch_316_vfd_fan_dynamic.py            # 试运行
    python.exe tools/byte_patch_316_vfd_fan_dynamic.py --apply    # 写入
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
                "B-加减载动态化",
                "\tif(LoadCondTemp > 360)\n"
                "\t{\n"
                "\t\tif(OutdoorVfdLoadCount < 30) OutdoorVfdLoadCount += uc1s;\n"
                "\t\tOutdoorVfdUnloadCount = 0;\n"
                "\t}\n"
                "\telse if(UnloadCondTemp < 340)\n"
                "\t{\n"
                "\t\tif(OutdoorVfdUnloadCount < 30) OutdoorVfdUnloadCount += uc1s;\n"
                "\t\tOutdoorVfdLoadCount = 0;\n"
                "\t}\n"
                "\telse\n"
                "\t{\n"
                "\t\tOutdoorVfdLoadCount = 0;\n"
                "\t\tOutdoorVfdUnloadCount = 0;\n"
                "\t}\n"
                "\tNeedLoad = (OutdoorVfdLoadCount >= 30) ? 1 : 0;\n"
                "\tNeedUnload = (OutdoorVfdUnloadCount >= 30) ? 1 : 0;\n",
                "\t/* 20260917 V12.10: 变频风机加减载是动态的 —— 冷凝 >36.0 每秒加、\n"
                "\t   <34.0 每秒减，34~36 之间保持（这个带就是规格书给的迟滞）。\n"
                "\t   原来「必须保持 30 秒才开始动作」的计数确认已去掉；两个计数变量\n"
                "\t   保留成 0/1，只为调试口能看出当前是加载/减载/保持哪一态。 */\n"
                "\tif(LoadCondTemp > 360)\n"
                "\t{\n"
                "\t\tOutdoorVfdLoadCount = 1;\n"
                "\t\tOutdoorVfdUnloadCount = 0;\n"
                "\t}\n"
                "\telse if(UnloadCondTemp < 340)\n"
                "\t{\n"
                "\t\tOutdoorVfdUnloadCount = 1;\n"
                "\t\tOutdoorVfdLoadCount = 0;\n"
                "\t}\n"
                "\telse\n"
                "\t{\n"
                "\t\tOutdoorVfdLoadCount = 0;\n"
                "\t\tOutdoorVfdUnloadCount = 0;\n"
                "\t}\n"
                "\tNeedLoad = (OutdoorVfdLoadCount) ? 1 : 0;\n"
                "\tNeedUnload = (OutdoorVfdUnloadCount) ? 1 : 0;\n",
            ),
            (
                "A-类型2不停机",
                "\t\telse if(NeedUnload && OutdoorVfdOn)\n"
                "\t\t{\n"
                "\t\t\tif((OutdoorVfdSpeed > MinSpeed) && uc1s)\n"
                "\t\t\t{\n"
                "\t\t\t\tOutdoorVfdSpeed -= Step;\n"
                "\t\t\t}\n"
                "\t\t\telse if((OutdoorFanRunSeconds[0] >= FanMinRunTimeSet)\n"
                "\t\t\t\t&& (OutdoorFanChangeSeconds >= 15))\n"
                "\t\t\t{\n"
                "\t\t\t\tOutdoorVfdOn = 0;\n"
                "\t\t\t\tOutdoorVfdSpeed = 0;\n"
                "\t\t\t\tOutdoorFanChangeSeconds = 0;\n"
                "\t\t\t}\n"
                "\t\t}\n",
                "\t\telse if(NeedUnload && OutdoorVfdOn)\n"
                "\t\t{\n"
                "\t\t\t/* 20260917 V12.10: 减载只减到【变频轴流风机最低频】为止。\n"
                "\t\t\t   本函数只在有压缩机运行时被调用，所以变频风机不允许停机。 */\n"
                "\t\t\tif((OutdoorVfdSpeed > MinSpeed) && uc1s)\n"
                "\t\t\t{\n"
                "\t\t\t\tOutdoorVfdSpeed -= Step;\n"
                "\t\t\t}\n"
                "\t\t}\n",
            ),
            (
                "A-类型4不停机",
                "\t\t\telse\n"
                "\t\t\t{\n"
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
                "\t\t\telse\n"
                "\t\t\t{\n"
                "\t\t\t\t/* 20260917 V12.10: 同上 —— 变频风机减到最低频为止，不停机。\n"
                "\t\t\t\t   类型4 里定速风机的起停仍按原分段逻辑，未动。 */\n"
                "\t\t\t\tif(OutdoorVfdOn && (OutdoorVfdSpeed > MinSpeed))\n"
                "\t\t\t\t{\n"
                "\t\t\t\t\tif(uc1s) OutdoorVfdSpeed -= Step;\n"
                "\t\t\t\t}\n"
                "\t\t\t}\n",
            ),
        ],
        "变频风机：加减载改成动态 + 不再停机",
    ),
    (
        "User/User.h",
        [
            (
                "版本号",
                "#define PSC316_VERSION_MINOR 9\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
                "#define PSC316_VERSION_MINOR 10\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
            ),
            (
                "版本历史",
                "\n */\n#define PSC316_VERSION_MODEL 316\n",
                "\n"
                "   V12.9 -> V12.10 (2026-09-17)：变频风机（类型2 单风机变频 / 类型4 变频+定速）\n"
                "       两条，按用户规格书解读拍板：\n"
                "       A「减到低频为止、不停机」—— 所在外机只要有压缩机在运行，变频风机就不许停机。\n"
                "         OutdoorFanTypeIII() 只在有压机运行时被调用，所以删掉两处\n"
                "         `OutdoorVfdOn = 0` 停机分支，减载减到【变频轴流风机最低频】为止，\n"
                "         由函数末尾 `if(OutdoorVfdOn && (Speed < MinSpeed)) Speed = MinSpeed;` 兜住。\n"
                "       B「加减载是动态的」—— 原来要 OutdoorVfdLoadCount/UnloadCount 累到 30 才\n"
                "         置 NeedLoad/NeedUnload，等于每次加减载前先干等 30 秒。改成直接按冷凝温度判：\n"
                "         冷凝 >36.0 每秒加、<34.0 每秒减、34~36 之间保持（该带即规格书给的迟滞）。\n"
                "         两个计数变量保留成 0/1，只为调试口能看出当前处于哪一态。\n"
                "       未动：「若风机没开、冷凝 >45 度满频」里的 30 秒确认（ForceFull）—— 用户只说了加减载。\n"
                "       影响面：只影响风机类型2 / 类型4；类型0/1/3 未动。\n"
                " */\n#define PSC316_VERSION_MODEL 316\n",
            ),
        ],
        "版本号 V12.9 -> V12.10，并补版本历史",
    ),
]


def main() -> int:
    print("=" * 74)
    print("V12.10 变频风机：加减载动态化 + 有压机就不断风机" + ("   [APPLY]" if APPLY else "   [试运行]"))
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
