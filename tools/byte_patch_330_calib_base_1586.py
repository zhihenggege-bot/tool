"""330 固件 V10.6：温度校准镜像块基址 1506 -> 1586。

背景：316 V12.7 把温度校准镜像块从 `Parameter[1500..1521]` 整体下移到
`1580..1601`（见 316 `UserAction.c` 的 `Parameter[1580+i]`、`User.h` 的版本注释）。
330 侧还在用旧基址，于是校准写进死区：**330 写完后用自己的值更新镜像
（`PSC316StatusMirror`），工具回读一致、报"写入成功"，但 316 已经不看那块了。**

改动三处（都在 `modulecontrol.c`）+ 版本号：
  - `PSC316Gateway_HMIWrite()`       写目标 `1506 + offset`      -> `1586`
  - `PSC316Gateway_HandleWriteReadback()` 镜像更新范围与偏移      -> `1586` / `1593`

⚠ **本仓库的源文件编码是混的**：`User.h` / `modulecontrol.c` / `user.c` 是 UTF-8，
`ErrorCheck.c` 是 GBK。**改前必须按文件探测编码**，否则中文注释会被写成乱码
（这次就踩过：按 GBK 往 UTF-8 的 `User.h` 里插注释，两边都解不开了）。
本脚本每步都先探测，纯 ASCII 的代码替换用字节级操作（编码无关）。

跑法：
    python.exe tools/byte_patch_330_calib_base_1586.py [--apply]
不带 --apply 只检查不写入。已打过补丁的项会报 SKIP，可反复跑。
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "PSC330RK-V10-内机"
MC = ROOT / "User" / "UserSrc" / "modulecontrol.c"
UH = ROOT / "User" / "UserHead" / "User.h"

APPLY = "--apply" in sys.argv
problems = 0


def detect_encoding(path: pathlib.Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "gbk"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"{path.name}: 既不是 UTF-8 也不是 GBK（可能已被写坏）")


def swap(data: bytes, old: bytes, new: bytes, label: str) -> bytes:
    """字节级替换，要求恰好命中一次。"""
    global problems
    n = data.count(old)
    if n == 0 and data.count(new) == 1:
        print(f"[SKIP] {label}: 已是目标值")
    elif n == 1:
        data = data.replace(old, new)
        print(f"[OK  ] {label}")
    else:
        print(f"[FAIL] {label}: 命中 {n} 次（应为 1 次）")
        problems += 1
    return data


def main() -> int:
    global problems  # 下面的自检里会 +=，不声明的话整个 main 里它都算局部变量

    # ---------- modulecontrol.c（UTF-8，但只动纯 ASCII，编码无关） ----------
    mc_enc = detect_encoding(MC)
    print(f"modulecontrol.c 编码 = {mc_enc}")
    mc = MC.read_bytes()
    mc = swap(mc, b"targetAddr = 1506 + offset;", b"targetAddr = 1586 + offset;",
              "写目标 1506 -> 1586")
    mc = swap(mc, b"(PSC316WriteJob.addr >= 1506) && (PSC316WriteJob.addr <= 1513)",
              b"(PSC316WriteJob.addr >= 1586) && (PSC316WriteJob.addr <= 1593)",
              "镜像更新范围 1506..1513 -> 1586..1593")
    mc = swap(mc, b"offset = PSC316WriteJob.addr - 1506;",
              b"offset = PSC316WriteJob.addr - 1586;",
              "镜像更新偏移 1506 -> 1586")

    # ---------- User.h（UTF-8 + CRLF）：版本号 + 版本注释 ----------
    uh_enc = detect_encoding(UH)
    print(f"User.h 编码 = {uh_enc}")
    uh = UH.read_bytes()
    uh = swap(uh, b"#define PSC330_VERSION_MINOR        5",
              b"#define PSC330_VERSION_MINOR        6", "VERSION_MINOR 5 -> 6")
    uh = swap(uh, b"#define PSC330_VERSION_DAY          15",
              b"#define PSC330_VERSION_DAY          16", "VERSION_DAY 15 -> 16")

    anchor = b"\xe3\x80\x82 */\r\n#define PSC330_VERSION_MODEL"
    if b"V10.5 -> V10.6" in uh:
        print("[SKIP] 版本注释: 已追加")
    elif uh.count(anchor) == 1:
        # 锚点里带了原来的 "。 */"，替换文本**不能**再以 " */" 开头 —— 那样注释会在
        # 这一行就闭合，后面几行全变成代码（这次编译就是这么炸的，一堆 #7: unrecognized token）。
        note = (
            "\r\n"
            "   V10.4 -> V10.5 (2026-09-15)：外机号越界保护 + 写任务停滞超时放弃（11acb08）。\r\n"
            "   V10.5 -> V10.6 (2026-09-16)：温度校准镜像块基址 1506 -> 1586。\r\n"
            "   316 V12.7 把该块从 1500..1521 下移到 1580..1601，330 侧写目标与镜像更新\r\n"
            "   必须同步 +80；否则校准写进死区 —— 330 用自己的值更新镜像，回读一致、\r\n"
            "   工具报成功，316 却不再看那块。\r\n"
            "   */\r\n#define PSC330_VERSION_MODEL"
        ).encode(uh_enc)
        uh = uh.replace(anchor, note)
        print("[OK  ] 版本注释追加 V10.5 / V10.6 两行")
    else:
        print(f"[FAIL] 版本注释: 锚点命中 {uh.count(anchor)} 次")
        problems += 1

    if APPLY and not problems:
        MC.write_bytes(mc)
        UH.write_bytes(uh)
        print("\n已写入。")
    else:
        print(f"\n{'未写入（加 --apply 生效）' if not problems else '有失败项，未写入'}")

    # ---------- 收尾自检 ----------
    if APPLY and not problems:
        for path, enc in ((MC, mc_enc), (UH, uh_enc)):
            raw = path.read_bytes()
            try:
                raw.decode(enc)
                ok = "编码 OK"
            except UnicodeDecodeError as exc:
                ok = f"!! 编码坏了: {exc}"
                problems += 1
            print(f"  自检 {path.name}: 1586×{raw.count(b'1586')} "
                  f"残留1506×{raw.count(b'1506')}  {ok}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
