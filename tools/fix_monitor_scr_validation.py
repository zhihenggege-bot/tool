# -*- coding: utf-8 -*-
"""把监控工具 app.py 里两条过时的输出冲突校验 + 一批过时文案，对齐到 V10.11 固件。

背景（2026-09-20）：
  §25 把可控硅从「独占 3 路模拟量、制热预热共用」改成「制热一套、预热一套」：
     制热/再热/辅热  DA0（共用=否 时 DA9）+ Y0/Y1
     预热            DA1 + Y15/Y16
  §25.4 第 2 条明写「删除 sharedConflict 分支……互不抢口」，
  固件 `IndoorUpdateAOConflict()` 也不再上报 INDOOR_AO_CONFLICT_HEAT_SCR(0x01)。

  但监控工具还停在旧模型，导致两个方向的错：

  1) 【误拦】`_validate_mode_config` 里 `reheat_mode == 4 and preheat_mode == 4`
     直接拒绝 —— 这在旧的三区段模型下成立，现在再热/辅热走 DA0/DA9、预热走 DA1，
     零重叠。用户实测被这条挡住，写不进 [129]。
     ⇒ 整条删除（新版下该组合不冲突）。

  2) 【漏放】备注 4 的校验写成 `[128] in (3,4)` × `reheat_mode in (2,3)`，
     固件 `separateStageConflict` 是 `{3,4,5}` × `{2,3,4}` —— 两头都漏了可控硅。
     结果是 `[128]=5 + [332]=4 + [129]=0` 会被**放行**，而固件里 heatAllow=0、
     再热被静默掐掉（界面上无任何提示）。
     ⇒ 补成 (3, 4, 5) × (2, 3, 4)。

  3) 一批寄存器文案还写着旧的三区段（DA0=0~40% / DA1=40~70% / DA9=70~100%）。
     另：[507] DA1ValueDisp 是**死寄存器**（固件全仓只写 0），DA1 真实值在 [915]。

⚠ app.py 是 UTF-8 **带 BOM** + **全 CRLF**，但字节干净（U+FFFD=0）。
  本脚本按字节改，改完核对 行数 与 U+FFFD。

跑法：
    python.exe tools/fix_monitor_scr_validation.py            # 干跑
    python.exe tools/fix_monitor_scr_validation.py --apply    # 真改
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

APP = (pathlib.Path(__file__).resolve().parent.parent
       / "psc330_monitor_tool" / "psc330_monitor" / "app.py")

CRLF = "\r\n"
problems: list[str] = []


def swap(data: bytes, old: str, new: str, label: str) -> bytes:
    ob, nb = old.encode("utf-8"), new.encode("utf-8")
    n = data.count(ob)
    if n != 1:
        print("  [FAIL] %-44s 锚点命中 %d 次（预期 1）" % (label, n))
        problems.append(label)
        return data
    print("  [OK  ] %-44s  -%d/+%d 字节" % (label, len(ob), len(nb)))
    return data.replace(ob, nb)


# ---- 1) 删掉过时的「再热/辅热 + 预热 都选可控硅」冲突（含整行前导缩进）----
E1_OLD = (
    "        if reheat_mode == 4 and preheat_mode == 4:" + CRLF +
    '            raise ValueError("DA0/DA1/DA9冲突：再热/辅热和预热不能同时选择1:1:1可控硅输出。")' + CRLF
)

# ---- 2a) 备注 4：补上可控硅（固件是 {3,4,5} × {2,3,4}）----
E2A_OLD = (
    "            and raw_values[128] in (3, 4)" + CRLF +
    "            and reheat_mode in (2, 3)" + CRLF
)
E2A_NEW = (
    "            and raw_values[128] in (3, 4, 5)" + CRLF +
    "            and reheat_mode in (2, 3, 4)" + CRLF
)

# ---- 2b) 备注 4 的报错文案：点明是"同一组分段口"，且可控硅也算 ----
E2B_OLD = ('            raise ValueError("制热与再热不共用时，制热和再热不能同时选择分段电加热输出。")')
E2B_NEW = ('            raise ValueError(' + CRLF +
           '                "制热与再热/辅热不共用时，两边不能同时占同一组分段口"\r\n'
           '                "（1:2分段 / 1:2:4分段 / 1:1:1可控硅 都要用 Y0/Y1）。"\r\n'
           '            )')

# ---- 3) 过时文案 ----
E3_OLD = ('    RegisterDef(914, "最终 DA0 再热/辅热/SCR第1组", formatter=fmt_da_voltage, '
          'unit="0-10V", note="1:1:1可控硅的0~40%区段；40%加载、30%减载"),')
E3_NEW = ('    RegisterDef(914, "最终 DA0 制热/再热/辅热 AO", formatter=fmt_da_voltage, '
          'unit="0-10V", note="共用=否 时再热/辅热改走 DA9；可控硅模式下是余数通道 '
          'AO=clamp(demand−300·组1−300·组2, 0, 400)×1000/400"),')

E4_OLD = ('    RegisterDef(915, "最终 DA1 预热/共享加热/SCR第2组", formatter=fmt_da_voltage, '
          'unit="0-10V", note="1:1:1可控硅的40~70%区段；70%加载、60%减载"),')
E4_NEW = ('    RegisterDef(915, "最终 DA1 预热 AO", formatter=fmt_da_voltage, '
          'unit="0-10V", note="预热专用；可控硅模式下是余数通道（组1/组2 走 Y15/Y16）"),')

E5_OLD = ('    RegisterDef(923, "最终 DA9 加热/SCR第3组", formatter=fmt_da_voltage, '
          'unit="0-10V", note="1:1:1可控硅的70~100%区段"),')
E5_NEW = ('    RegisterDef(923, "最终 DA9 再热/辅热专用 AO", formatter=fmt_da_voltage, '
          'unit="0-10V", note="〖制热与再热/辅热是否共用〗=否 时再热/辅热走这里；'
          '共用=是 时恒为 0"),')

E6_OLD = '    RegisterDef(507, "AO1/DA1 显示", formatter=fmt_da_voltage, unit="0-10V"),'
E6_NEW = ('    RegisterDef(507, "AO1/DA1 显示（废弃）", formatter=fmt_da_voltage, '
          'unit="0-10V", note="⚠ 固件全仓不写此寄存器，恒为 0；DA1 真实值看 [915]"),')

E7_OLD = '                (0x01, "加热/再热与预热的AO因SCR复用DA0/DA1/DA9"),'
E7_NEW = '                (0x01, "（固件已停用此位）加热/再热与预热的AO因SCR复用DA0/DA1/DA9"),'

E8_OLD = '                3: "普通再热DA0 + 普通预热DA1同时输出",'
E8_NEW = '                3: "制热/再热/辅热 + 预热 同时输出（各占各的口）",'

E9_OLD = '        note="发生SCR复用冲突时预热优先，避免低温预热保护被静默清零",'
E9_NEW = ('        note="制热/再热/辅热占 DA0/DA9 + Y0/Y1，预热占 DA1 + Y15/Y16，'
          '互不抢口、可同时输出",')

EDITS = [
    (E1_OLD, "", "删过时校验「再热/辅热+预热 双可控硅」"),
    (E2A_OLD, E2A_NEW, "备注4 校验补 (3,4,5)×(2,3,4)"),
    (E2B_OLD, E2B_NEW, "备注4 报错文案"),
    (E3_OLD, E3_NEW, "[914] 文案"),
    (E4_OLD, E4_NEW, "[915] 文案"),
    (E5_OLD, E5_NEW, "[923] 文案"),
    (E6_OLD, E6_NEW, "[507] 废弃标注"),
    (E7_OLD, E7_NEW, "[940] bit0 停用标注"),
    (E8_OLD, E8_NEW, "[941] 值3 文案"),
    (E9_OLD, E9_NEW, "[941] note"),
]


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def main() -> int:
    apply = "--apply" in sys.argv
    data = APP.read_bytes()
    orig = data

    print("改前：")
    print("  app.py  sha=%s  bytes=%d  lines=%d  U+FFFD=%d"
          % (sha(APP), len(data), data.count(b"\r\n") + 1, data.count(b"\xef\xbf\xbd")))
    print()
    print("编辑：")
    for old, new, label in EDITS:
        data = swap(data, old, new, label)

    if problems:
        print("\n[X] 有锚点没命中，未写入任何文件。")
        return 1

    # 自检：改完必须仍是干净 UTF-8、无 U+FFFD、行数差符合预期
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        print("\n[X] 改后不是合法 UTF-8：%s" % exc)
        return 1
    if data.count(b"\xef\xbf\xbd"):
        print("\n[X] 改后出现 U+FFFD（编码损坏），未写入。")
        return 1
    try:
        # compile() 不认 UTF-8 BOM（app.py 有），剥掉再查语法
        compile(text.lstrip("﻿"), str(APP), "exec")
    except SyntaxError as exc:
        print("\n[X] 改后语法错误：%s" % exc)
        return 1

    d_lines = data.count(b"\r\n") - orig.count(b"\r\n")
    print()
    print("改后：")
    print("  app.py  bytes=%d (%+d)  lines=%d (%+d)  U+FFFD=%d"
          % (len(data), len(data) - len(orig), data.count(b"\r\n") + 1, d_lines,
             data.count(b"\xef\xbf\xbd")))
    print("  语法检查通过")

    if apply:
        APP.write_bytes(data)
        print("\n已写入：app.py  sha=%s" % sha(APP))
    else:
        print("\n（干跑，未写入。加 --apply 生效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
