"""从固件源码导出 316 的制冷剂「压力 -> 饱和温度」表，生成两样东西：

    1. psc330_monitor_tool/psc330_monitor/pt_tables.py   给监控工具用
    2. 冷凝温度对照表_316.md                              给人看的对照表

数据源是 PSC316RK-V12-外机/WELLTHINKER/User/TempFilter.c 里的
R22Temp[385] / R134ATemp[385] / R407CTemp[385] / R410ATemp[872]，
换算公式照抄 UserAction.c 的 OutdoorPTTempFromPressure()。

固件一改表就得重跑这个脚本，保证工具侧和板子上的值逐位一致。

跑法：
    python.exe tools/gen_pt_tables.py
    python.exe tools/gen_pt_tables.py --check     # 只做一致性自检，不写文件
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "PSC316RK-V12-外机" / "WELLTHINKER" / "User" / "TempFilter.c"
OUT_PY = ROOT / "psc330_monitor_tool" / "psc330_monitor" / "pt_tables.py"
OUT_MD = ROOT / "冷凝温度对照表_316.md"

SIZE = {"R22Temp": 385, "R134ATemp": 385, "R407CTemp": 385, "R410ATemp": 872}
LABEL = {"R22Temp": "R22", "R134ATemp": "R134A", "R407CTemp": "R407C", "R410ATemp": "R410A"}
REF = {"R22Temp": 0, "R134ATemp": 1, "R407CTemp": 2, "R410ATemp": 3}
CHECK_ONLY = "--check" in sys.argv


def load_tables() -> tuple[dict[str, list[int]], str]:
    raw = SRC.read_bytes()
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"{SRC.name}: 既不是 UTF-8 也不是 GBK")
    tables = {}
    for name, size in SIZE.items():
        m = re.search(r"const\s+signed\s+short\s+%s\[%d\]\s*=\s*\{(.*?)\};" % (name, size), text, re.S)
        if not m:
            raise RuntimeError(f"没找到 {name}[{size}]")
        body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
        values = [int(x) for x in re.findall(r"-?\d+", body)]
        if len(values) != size:
            raise RuntimeError(f"{name}: 解析出 {len(values)} 项，声明是 {size}")
        tables[name] = values
    return tables, enc


# 钳位（照固件）：R410A 到 j=870，其余到 j=383
CAP = {"R22Temp": 383, "R134ATemp": 383, "R407CTemp": 383, "R410ATemp": 870}


def pt_x10(values: list[int], cap: int, kpa: int) -> int:
    """与固件 OutdoorPTTempFromPressure() 等价的整数算法。"""
    if kpa < 0:
        kpa = 0
    j = (kpa + 100) // 5
    if j >= cap:
        j = cap
    if j < 0:
        j = 0
    rem = kpa % 5
    return values[j] + rem * (values[j + 1] - values[j]) // 5


def write_py(tables: dict[str, list[int]]) -> None:
    L: list[str] = []
    L.append('"""PSC316 制冷剂 压力 -> 饱和温度 对照表（自动生成，勿手改）。')
    L.append("")
    L.append("数据源：PSC316RK-V12-外机/WELLTHINKER/User/TempFilter.c 的")
    L.append("        R22Temp[385] / R134ATemp[385] / R407CTemp[385] / R410ATemp[872]")
    L.append("用法  ：UserAction.c 的 OutdoorPTTempFromPressure()，被 OutdoorCondTemps() 用于")
    L.append("        机型 != 0 时由高压传感器算「冷凝温度」。")
    L.append("")
    L.append("换算规则（与固件逐字一致）：")
    L.append("    j = (kPa + 100) // 5        # 每格 5 kPa")
    L.append("    rem = kPa % 5               # 格内线性插值")
    L.append("    温度x10 = table[j] + rem * (table[j+1] - table[j]) // 5")
    for name, cap in CAP.items():
        L.append("    %-6s 钳位 j<=%d（-> %d kPa / %.1f bar / %.1f C）"
                 % (LABEL[name], cap, 5 * cap - 100, (5 * cap - 100) / 100.0,
                    pt_x10(tables[name], cap, 10 ** 7) / 10.0))
    L.append("")
    L.append("重新生成：python.exe tools/gen_pt_tables.py")
    L.append('"""')
    L.append("")
    L.append("from __future__ import annotations")
    L.append("")
    L.append("# 制冷剂编号，与 316 的 RefrigerantSetP02 = Parameter[PROTECT+14] = Parameter[39] 一致")
    L.append("R22, R134A, R407C, R410A = 0, 1, 2, 3")
    L.append('REFRIGERANT_NAMES = {R22: "R22", R134A: "R134A", R407C: "R407C", R410A: "R410A"}')
    L.append("")
    for name in SIZE:
        values = tables[name]
        L.append("# %s" % LABEL[name])
        L.append("_%s = (" % LABEL[name])
        for k in range(0, len(values), 20):
            L.append("    " + " ".join("%d," % x for x in values[k:k + 20]))
        L.append(")")
        L.append("")
    L.append("_TABLES = {%s}" % ", ".join("%s: _%s" % (LABEL[n], LABEL[n]) for n in SIZE))
    L.append("")
    L.append("# 钳位（照固件）：R410A 到 j=870，其余到 j=383")
    L.append("_CAP = {%s}" % ", ".join("%s: %d" % (LABEL[n], CAP[n]) for n in SIZE))
    L.append("")
    L.append("")
    L.append("def pt_temp_x10(refrigerant: int, kpa: int) -> int:")
    L.append('    """压力(kPa) -> 饱和温度(x10, 即 0.1C)。与固件 OutdoorPTTempFromPressure() 等价。"""')
    L.append("    table = _TABLES.get(refrigerant)")
    L.append("    if table is None:")
    L.append("        table = _TABLES[R410A]      # 固件的 else 分支就是 R410A")
    L.append("    cap = _CAP.get(refrigerant, 383)")
    L.append("    if kpa < 0:")
    L.append("        kpa = 0")
    L.append("    j = (kpa + 100) // 5")
    L.append("    if j >= cap:")
    L.append("        j = cap")
    L.append("    if j < 0:")
    L.append("        j = 0")
    L.append("    rem = kpa % 5")
    L.append("    return table[j] + rem * (table[j + 1] - table[j]) // 5")
    L.append("")
    L.append("")
    L.append("def pt_temp(refrigerant: int, kpa: int) -> float:")
    L.append('    """压力(kPa) -> 饱和温度(C)，浮点。"""')
    L.append("    return pt_temp_x10(refrigerant, kpa) / 10.0")
    L.append("")
    L.append("")
    L.append("def pressure_max_kpa(refrigerant: int) -> int:")
    L.append('    """该制冷剂表能表示的最大压力（超过就钳位，温度不再上升）。"""')
    L.append("    return 5 * _CAP.get(refrigerant, 383) - 100")
    L.append("")
    OUT_PY.write_text("\n".join(L), encoding="utf-8")
    print("已写 %s  (%d 行, %d 字节)" % (OUT_PY.name, len(L), OUT_PY.stat().st_size))


def write_md(tables: dict[str, list[int]]) -> None:
    L: list[str] = []
    L.append("# PSC316 制冷剂 压力 -> 饱和温度 对照表")
    L.append("")
    L.append("由 `tools/gen_pt_tables.py` 从固件源码导出，与板子上逐位一致。")
    L.append("")
    L.append("| 项 | 说明 |")
    L.append("|---|---|")
    L.append("| 数据源 | `PSC316RK-V12-外机/WELLTHINKER/User/TempFilter.c` |")
    L.append("| 换算函数 | `UserAction.c` `OutdoorPTTempFromPressure()` |")
    L.append("| 谁在用 | `OutdoorCondTemps()` —— **机型≠0** 时用高压传感器算「冷凝温度」；机型0 改用翅片温度 |")
    L.append("| 索引 | `j = (kPa + 100) / 5`，**每格 5 kPa**，格内线性插值 |")
    L.append("| 压力单位 | kPa（1 LSB = 1 kPa = 0.01 bar），GB 压力量程 `Parameter[52]` 默认 4600 |")
    L.append("| 制冷剂选择 | `RefrigerantSetP02 = Parameter[PROTECT+14] = Parameter[39]`：0=R22 1=R134A 2=R407C 3=R410A |")
    L.append("")
    L.append("## 各表覆盖范围")
    L.append("")
    L.append("| 制冷剂 | 表项数 | 有效压力 | 封顶温度 |")
    L.append("|---|---:|---:|---:|")
    for name in SIZE:
        cap = CAP[name]
        p_max = 5 * cap - 100
        L.append("| %s | %d | 0 ~ %d kPa（0 ~ %.2f bar）| %.1f ℃ |"
                 % (LABEL[name], SIZE[name], p_max, p_max / 100.0,
                    pt_x10(tables[name], cap, 10 ** 7) / 10.0))
    L.append("")
    L.append("> 超过封顶压力后温度**钳位不再上升**（`if(j >= cap) j = cap;`）。")
    L.append("")
    for name in SIZE:
        values, cap = tables[name], CAP[name]
        p_max = 5 * cap - 100
        L.append("## %s" % LABEL[name])
        L.append("")
        L.append("| bar | kPa | 饱和温度 ℃ | 温度x10 |")
        L.append("|---:|---:|---:|---:|")
        for kpa in list(range(0, p_max, 50)) + [p_max]:
            L.append("| %.2f | %d | %.1f | %d |"
                     % (kpa / 100.0, kpa, pt_x10(values, cap, kpa) / 10.0, pt_x10(values, cap, kpa)))
        L.append("")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print("已写 %s  (%d 行)" % (OUT_MD.name, len(L)))


def self_check(tables: dict[str, list[int]]) -> int:
    """生成的 pt_tables.py 与固件算法逐点比对。"""
    if not OUT_PY.exists():
        print("!! pt_tables.py 不存在，跳过自检")
        return 1
    import importlib.util
    spec = importlib.util.spec_from_file_location("pt_check", OUT_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    bad = 0
    for name in SIZE:
        cap = CAP[name]
        ref = REF[name]
        for kpa in range(0, 5001, 7):
            if pt_x10(tables[name], cap, kpa) != mod.pt_temp_x10(ref, kpa):
                bad += 1
                if bad <= 3:
                    print("   !! %s %d kPa: 固件 %d vs 模块 %d"
                          % (LABEL[name], kpa, pt_x10(tables[name], cap, kpa), mod.pt_temp_x10(ref, kpa)))
    print("逐点自检（0~5000 kPa 每 7 kPa × 4 种制冷剂）：不一致 %d 处" % bad)
    return 1 if bad else 0


def main() -> int:
    tables, enc = load_tables()
    print("读 %s (enc=%s)" % (SRC.name, enc))
    for name in SIZE:
        values = tables[name]
        print("  %-6s %4d 项  首=%6d 末=%6d" % (LABEL[name], len(values), values[0], values[-1]))
    if CHECK_ONLY:
        return self_check(tables)
    write_py(tables)
    write_md(tables)
    return self_check(tables)


if __name__ == "__main__":
    sys.exit(main())
