"""V12.12：变频风机**预启动**也要判冷凝温度。

规格书：**若风机没开，冷凝温度大于45度满频。**

V12.11 改的是 `OutdoorFanTypeIII()` 里的启动分支，但实测（外机1 机型1/类型2，
ST-Link 复位后冷凝假报 47.0C）发现那条分支**永远轮不到**：

    压机全停 + 有启动请求  ->  OutdoorBoardFanControl 走
        OutdoorFanPrestart()  ->  OutdoorFanPrestartVfd()   // 固定给 MinSpeed
    预启动已把 OutdoorVfdOn 置 1
    压机起来 -> OutdoorFanTypeIII() 里 !OutdoorVfdOn 为假 -> 启动块不执行
    -> 只能靠 NeedLoad(冷凝>36) 以 2.0Hz/s 慢慢爬：20.0Hz 起，约 15 秒才到 50.0Hz

实测序列就是这么走的，与规格书的「满频」不符。

改法：预启动时也按冷凝温度给频率。
   OutdoorVfdSpeed = (OutdoorCondTempMax() > 450) ? MaxSpeed : MinSpeed;

顺带补一个保护：原来只有 `if(MinSpeed <= 0) MinSpeed = 10;`，没有 MaxSpeed 的下限。
若「变频轴流风机最高频」被设成 0 或低于最低频，MaxSpeed 会 < MinSpeed —— 而刚置
OutdoorVfdOn=1 的这一次**不经过**下面那个 `else if(OutdoorVfdSpeed < MinSpeed)`，
不兜就会把预启动速度设到最低频以下。
   if(MaxSpeed < MinSpeed) MaxSpeed = MinSpeed;

影响面：
  * 类型2（单风机变频）与 类型4（变频+定速）共用这个函数，两者都生效（用户确认要一起）
  * 类型0/1/3 不走这个函数，不受影响
  * 制热 `OutdoorFanHeatPump()` 本来就对类型2/4 直接给满频，不受影响
  * 调用点只有 `OutdoorFanPrestart()` 的 1109（类型2）/ 1123（类型4），
    而 `OutdoorFanPrestart()` 只在「压机全停 + 启动挂起」分支被调

编码：UserAction.c / User.h = UTF-8 + CRLF、无 BOM。按字节替换，写回后回读校验。

跑法：
    python.exe tools/byte_patch_316_prestart_cond_temp.py            # 试运行
    python.exe tools/byte_patch_316_prestart_cond_temp.py --apply    # 写入
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
                "预启动按冷凝温度给频率",
                "\tsigned int MinSpeed;\n"
                "\n"
                "\tMinSpeed = FanMinFreqSet * 10;\n"
                "\tif(MinSpeed <= 0) MinSpeed = 10;\n"
                "\tif(!OutdoorVfdOn)\n"
                "\t{\n"
                "\t\tif((OutdoorFanStopSeconds[0] >= FanMinStopTimeSet)\n"
                "\t\t\t&& (OutdoorFanChangeSeconds >= 15))\n"
                "\t\t{\n"
                "\t\t\tOutdoorVfdOn = 1;\n"
                "\t\t\tOutdoorVfdSpeed = MinSpeed;\n"
                "\t\t\tOutdoorFanChangeSeconds = 0;\n"
                "\t\t}\n"
                "\t}\n",
                "\tsigned int MinSpeed;\n"
                "\tsigned int MaxSpeed;\n"
                "\n"
                "\tMinSpeed = FanMinFreqSet * 10;\n"
                "\tif(MinSpeed <= 0) MinSpeed = 10;\n"
                "\tMaxSpeed = FanMaxFreqSet * 10;\n"
                "\t/* 最高频参数若被设成 0 或低于最低频，兜到最低频 —— 下面那个\n"
                "\t   else if(OutdoorVfdSpeed < MinSpeed) 只在 VfdOn 已经是 1 时才走，\n"
                "\t   刚置 VfdOn=1 的这一次不经过它，不兜就会把速度设到最低频以下。 */\n"
                "\tif(MaxSpeed < MinSpeed) MaxSpeed = MinSpeed;\n"
                "\tif(!OutdoorVfdOn)\n"
                "\t{\n"
                "\t\tif((OutdoorFanStopSeconds[0] >= FanMinStopTimeSet)\n"
                "\t\t\t&& (OutdoorFanChangeSeconds >= 15))\n"
                "\t\t{\n"
                "\t\t\tOutdoorVfdOn = 1;\n"
                "\t\t\t/* 20260917 V12.12: 规格书「若风机没开，冷凝温度大于45度满频」。\n"
                "\t\t\t   压机启动挂起时走的就是这个预启动，原来固定给最低频、不看冷凝\n"
                "\t\t\t   温度 —— 它会把 OutdoorFanTypeIII 里那个能判 >45 的启动分支彻底\n"
                "\t\t\t   绕过（预启动先把 VfdOn 置 1，那边 !OutdoorVfdOn 就为假了）。\n"
                "\t\t\t   实测（外机1 机型1/类型2，复位后冷凝 47.0C）：启动给 20.0Hz，\n"
                "\t\t\t   约 15 秒才爬到 50.0Hz，与规格书的「满频」不符。\n"
                "\t\t\t   类型4（变频+定速）共用这个函数，同样生效。 */\n"
                "\t\t\tOutdoorVfdSpeed = (OutdoorCondTempMax() > 450) ? MaxSpeed : MinSpeed;\n"
                "\t\t\tOutdoorFanChangeSeconds = 0;\n"
                "\t\t}\n"
                "\t}\n",
            ),
        ],
        "预启动 OutdoorFanPrestartVfd 判冷凝温度 + MaxSpeed 下限保护",
    ),
    (
        "User/User.h",
        [
            (
                "版本号",
                "#define PSC316_VERSION_MINOR 11\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
                "#define PSC316_VERSION_MINOR 12\n"
                "#define PSC316_VERSION_YEAR 2026\n"
                "#define PSC316_VERSION_MONTH 9\n"
                "#define PSC316_VERSION_DAY 17\n",
            ),
            (
                "版本历史",
                "\n */\n#define PSC316_VERSION_MODEL 316\n",
                "\n"
                "   V12.11 -> V12.12 (2026-09-17)：变频风机**预启动**也要判冷凝温度。\n"
                "       V12.11 改的是 OutdoorFanTypeIII() 里的启动分支，但实测发现那条分支\n"
                "       永远轮不到：压机全停 + 有启动请求时，OutdoorBoardFanControl 走\n"
                "       OutdoorFanPrestart() -> OutdoorFanPrestartVfd() 固定给最低频，\n"
                "       预启动先把 OutdoorVfdOn 置 1，等压机起来时那边 !OutdoorVfdOn 已为假。\n"
                "       实测（外机1 机型1/类型2，ST-Link 复位后冷凝假报 47.0C）：\n"
                "       启动给 20.0Hz，靠 NeedLoad(>36) 以 2.0Hz/s 爬，约 15 秒才到 50.0Hz，\n"
                "       与规格书「若风机没开，冷凝温度大于45度满频」不符。\n"
                "       改法：OutdoorVfdSpeed = (OutdoorCondTempMax() > 450) ? MaxSpeed : MinSpeed;\n"
                "       顺带补 MaxSpeed 下限保护（if(MaxSpeed < MinSpeed) MaxSpeed = MinSpeed;）——\n"
                "       原来只有 MinSpeed 的保护，而刚置 VfdOn=1 的这一次不经过下面那个\n"
                "       else if(OutdoorVfdSpeed < MinSpeed)。\n"
                "       影响面：类型2/类型4 共用此函数，两者都生效；类型0/1/3 与制热不受影响。\n"
                " */\n#define PSC316_VERSION_MODEL 316\n",
            ),
        ],
        "版本号 V12.11 -> V12.12，并补版本历史",
    ),
]


def main() -> int:
    print("=" * 74)
    print("V12.12 变频风机预启动也判冷凝温度" + ("   [APPLY]" if APPLY else "   [试运行]"))
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
