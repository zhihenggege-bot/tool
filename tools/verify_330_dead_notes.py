# -*- coding: utf-8 -*-
"""守住 PSC330 `User.h` 里那两段「死参数 / 死判据」注释所依赖的事实。

2026-09-21 按用户裁定给两个符号加了源码注释（只加注释，不进二进制）：
  - `ExhaustValveDelaySet = [135]`  零引用，延时硬编码在 IndoorValveOpenDelay()
  - `AntiFreezeErr       = [602]`   固件内无写入点，是 67726fb 拆分后的遗留孤儿

注释**不是**代码，编译器不会替我们检查它是否还说真话。一旦有人：
  - 把 `[135]` 真的接到时序上
  - 给 `AntiFreezeErr` 补回写入点（或把它删掉、改了读出点数量）
  - 改了 `IndoorValveOpenDelay()` 的返回值
注释就变成误导。本脚本把这些前提固化成断言，改固件后跑一次即可。

跑法： python.exe tools/verify_330_dead_notes.py
退出码 0 = 注释仍成立；1 = 有前提漂移，注释需要同步更新。
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FW = ROOT / "PSC330RK-V10-内机" / "User"
UH = FW / "UserHead" / "User.h"

# 只统计真正的源码；.bak / .codex-tmp / 分析文档都不算
SKIP_DIRS = {".codex-tmp", "before-encoding-repair"}


def sources() -> list[pathlib.Path]:
    out = []
    for f in sorted(FW.rglob("*")):
        if f.suffix.lower() not in (".c", ".h") or not f.is_file():
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        if f.name.endswith((".bak", ".v104bak", ".work")) or ".rename." in f.name:
            continue
        out.append(f)
    return out


def count(sym: str) -> list[tuple[pathlib.Path, int, str]]:
    """返回 [(文件, 行号, 行内容)]，行号由 split(b'\\n') 得出 —— 与 grep -n 一致。

    注释块要排除：本文件守护的那两段 NOTE 里**正文就写着符号名**
    （"moved; AntiFreezeErr was left behind…"），不排除会把自己数成一处引用。
    """
    hits = []
    for f in sources():
        in_note = False
        for i, line in enumerate(f.read_bytes().split(b"\n"), 1):
            if b"/* NOTE (2026-09-21)" in line:
                in_note = True
            if in_note:
                if b"*/" in line:
                    in_note = False
                continue
            if sym.encode() in line:
                hits.append((f, i, line.decode("gbk", "replace").rstrip("\r")))
    return hits


def main() -> int:
    fails: list[str] = []

    def check(cond: bool, ok: str, bad: str) -> None:
        print(("  [OK]   " if cond else "  [FAIL] ") + (ok if cond else bad))
        if not cond:
            fails.append(bad)

    uh = UH.read_bytes().decode("utf-8", "replace")

    print("[135] ExhaustValveDelaySet —— 注释前提：零引用")
    note = "DEAD PARAMETER - defined but never referenced anywhere in"
    check(note in uh, "注释仍在 User.h", "注释被删了")
    hits = count("ExhaustValveDelaySet")
    check(len(hits) == 1, "全仓仅定义处 1 次引用",
          "引用点变成 %d 处（有人接上了？同步注释）:\n%s"
          % (len(hits), "\n".join("      %s:%d  %s" % (f.name, i, s.strip()[:80])
                                  for f, i, s in hits)))

    print("\n[135] 注释前提：延时硬编码在 IndoorValveOpenDelay()")
    ua = (FW / "UserSrc" / "UserAction.c").read_text(encoding="gbk", errors="replace")
    m = re.search(r"IndoorValveOpenDelay\(void\)\s*\{(.{0,200}?)\}", ua, re.S)
    check(m is not None, "函数仍在", "IndoorValveOpenDelay() 找不到")
    if m:
        body = m.group(1)
        check("return 150;" in body, "仍返回 150（无阀时 10）",
              "返回值变了，注释里的 150s 说法失效：%s"
              % " ".join(body.split())[:120])
        check("ExhaustValveDelaySet" not in body,
              "函数里没有被 [135] 接管", "函数已引用 [135]，注释需改写")

    print("\nAntiFreezeErr —— 注释前提：固件内零写入、五处读出")
    note = "LEGACY ORPHAN - read in five places, written nowhere in the"
    check(note in uh, "注释仍在 User.h", "注释被删了")

    hits = count("AntiFreezeErr")
    defs = [h for h in hits if h[2].lstrip().startswith("#define")]
    writes = [h for h in hits if re.search(r"AntiFreezeErr\s*=[^=]", h[2])]
    reads = [h for h in hits if h not in defs and h not in writes]

    check(len(defs) == 1, "定义处 1 个", "定义处 %d 个" % len(defs))
    check(not writes, "无写入点（注释的核心断言）",
          "出现写入点 %d 处 —— 判据不再恒为 0，注释必须重写:\n%s"
          % (len(writes), "\n".join("      %s:%d  %s" % (f.name, i, s.strip()[:80])
                                    for f, i, s in writes)))
    check(len(reads) == 5, "读出点 5 处", "读出点 %d 处（注释写的是 5，需同步）:\n%s"
          % (len(reads), "\n".join("      %s:%d  %s" % (f.name, i, s.strip()[:80])
                                   for f, i, s in reads)))

    print("\nAntiFreezeErr 注释前提：功能已搬到 Supply/ReturnPressureFaultDisp")
    for sym in ("SupplyPressureFaultDisp", "ReturnPressureFaultDisp"):
        w = [h for h in count(sym) if re.search(sym + r"\s*=[^=]", h[2])]
        check(bool(w), "%s 有写入点（保护仍存在）" % sym,
              "%s 没有写入点 —— 注释里『保护还在，只是换了名字』不成立" % sym)

    print()
    if fails:
        print("!! %d 项前提漂移 —— 请同步 User.h 里的注释后重跑" % len(fails))
        return 1
    print("全部前提成立：User.h 的两段注释仍然说真话。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
