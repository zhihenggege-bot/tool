from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


ROOT = Path(__file__).resolve().parents[1]
STAMP = "20260907"
XLSX_PATH = ROOT / f"PSC330_PSC316_IO点位表_{STAMP}.xlsx"
CSV_PATH = ROOT / f"PSC330_PSC316_IO点位表_{STAMP}.csv"
MD_PATH = ROOT / f"PSC330_PSC316_IO点位说明_{STAMP}.md"
ZIP_PATH = ROOT / f"PSC330_PSC316_IO点位导出_{STAMP}.zip"

HEADERS = [
    "序号",
    "板卡",
    "类别",
    "物理点位",
    "物理/逻辑",
    "程序变量",
    "功能",
    "本机Modbus状态/工程值地址",
    "状态字位",
    "330网关镜像地址（1～4号外机）",
    "原始值地址",
    "配置/极性地址",
    "校准参数地址",
    "信号类型/量程",
    "单位",
    "读写属性",
    "复用/联锁说明",
    "备注",
    "源码依据",
]


def row(
    board: str,
    category: str,
    point: str,
    variable: str,
    function: str,
    local_address: str = "",
    bit: str = "",
    gateway: str = "",
    raw_address: str = "",
    config_address: str = "",
    calibration: str = "",
    signal: str = "",
    unit: str = "",
    access: str = "RO",
    reuse: str = "",
    note: str = "",
    source: str = "",
    physical: str = "物理点",
) -> dict[str, str]:
    return {
        "序号": "",
        "板卡": board,
        "类别": category,
        "物理点位": point,
        "物理/逻辑": physical,
        "程序变量": variable,
        "功能": function,
        "本机Modbus状态/工程值地址": local_address,
        "状态字位": bit,
        "330网关镜像地址（1～4号外机）": gateway,
        "原始值地址": raw_address,
        "配置/极性地址": config_address,
        "校准参数地址": calibration,
        "信号类型/量程": signal,
        "单位": unit,
        "读写属性": access,
        "复用/联锁说明": reuse,
        "备注": note,
        "源码依据": source,
    }


def gateway_addresses(offset: int) -> str:
    bases = (1550, 1620, 1690, 1760)
    return " / ".join(str(base + offset) for base in bases)


rows: list[dict[str, str]] = []

SRC330_IO = "PSC330RK-V10-内机/User/wellthinker/inc/io.h"
SRC330_USER = "PSC330RK-V10-内机/User/UserHead/User.h"
SRC330_ACTION = "PSC330RK-V10-内机/User/UserSrc/UserAction.c"
SRC330_NTC = "PSC330RK-V10-内机/User/NTC16bit/NTC16bit.c"
SRC316_IO = "PSC316RK-V12-外机/SYSTEM/inc/io.h"
SRC316_USER = "PSC316RK-V12-外机/WELLTHINKER/User/User.h"
SRC316_ACTION = "PSC316RK-V12-外机/WELLTHINKER/User/UserAction.c"
SRC316_NTC = "PSC316RK-V12-外机/WELLTHINKER/NTC16bit/NTC16bit.c"


# PSC330 DI
di330 = [
    ("X00", "X00 / PowerPhaseErrX0", "电源/相序保护", 1350, 155),
    ("X01", "X01 / FireAlarmX1", "消防报警", 1351, 156),
    ("X02", "X02 / FarSwitchX02", "远程启停/外部连锁输入", 1352, 157),
    ("X03", "X03 / PumpOverX00", "送风机/泵过载", 1353, 158),
    ("X04", "X04 / ValveLinkX4", "风阀联锁", 1354, 159),
    ("X05", "X05 / FilterBlocking", "过滤器堵塞/过滤器压差", 1355, 389),
    ("X06", "X06 / HeatFaultX6", "加热、再热或主加热故障", 1356, 390),
    ("X07", "X07", "预热故障", 1357, 391),
    ("X10", "X10", "加湿器故障", 1358, 392),
    ("X11", "X11", "排风机过载", 1359, 393),
    ("X12", "X12", "回风机过载", 1360, 394),
    ("X13", "X13", "漏水保护", 1361, 395),
    ("X14", "X14", "回风压差开关", 1362, 396),
    ("X15", "X15", "送风压差开关", 1363, 397),
]
for point, variable, function, status_addr, polarity_addr in di330:
    rows.append(
        row(
            "PSC330",
            "DI",
            point,
            variable,
            function,
            local_address=str(status_addr),
            config_address=str(polarity_addr),
            signal="开关量；极性0=反相/常闭断开报警，1=正相/常开闭合报警",
            access="状态RO；极性RW",
            note="状态地址显示的是固件采集后的点位状态；报警是否成立还受延时、模式和锁存逻辑影响。",
            source=f"{SRC330_IO}; {SRC330_USER}",
        )
    )

for point, status_addr in (("X16", 1364), ("X17", 1365)):
    rows.append(
        row(
            "PSC330",
            "DI",
            point,
            "无物理 input[] 项",
            "预留显示位",
            local_address=str(status_addr),
            signal="逻辑预留",
            access="RO",
            note="io.h 的 TOL_INPUT_CHANEL=14，仅定义X00～X15；该地址没有对应物理采样点。",
            source=f"{SRC330_IO}; psc330_monitor_tool/psc330_monitor/app.py",
            physical="逻辑预留",
        )
    )


# PSC330 DO
do330 = [
    ("Y00", "Y00", "再热/电加热1份", 814, "1:2:4分段最低权重"),
    ("Y01", "Y01", "再热/电加热2份", 815, "1:2:4分段中间权重"),
    ("Y02", "Y02", "再热/电加热4份", 816, "1:2:4分段最高权重"),
    ("Y03", "Y03", "送风机/送风输出", 817, ""),
    ("Y04", "Y04", "送风阀", 818, ""),
    ("Y05", "Y05", "综合报警输出", 819, ""),
    ("Y06", "Y06", "回风机", 820, ""),
    ("Y07", "Y07", "回风阀", 821, ""),
    ("Y10", "Y10", "排风机", 1366, ""),
    ("Y11", "Y11", "排风阀/热回收阀", 1367, "功能随系统配置复用"),
    ("Y12", "Y12", "消毒/杀菌装置", 1368, ""),
    ("Y13", "Y13", "加湿阀/开关型加湿输出", 1369, ""),
    ("Y14", "Y14", "新风阀", 1370, ""),
    ("Y15", "Y15", "新风预热1份", 1371, "1:2:4分段最低权重"),
    ("Y16", "Y16", "新风预热2份", 1372, "1:2:4分段中间权重"),
    ("Y17", "Y17", "新风预热4份", 1373, "1:2:4分段最高权重"),
]
for point, variable, function, status_addr, reuse in do330:
    rows.append(
        row(
            "PSC330",
            "DO",
            point,
            variable,
            function,
            local_address=str(status_addr),
            signal="继电器/开关量输出；0=断开，1=吸合",
            access="RO（状态监视）",
            reuse=reuse,
            note="分段1:2:4三路组合可形成约0/15/30/45/60/75/90/100%输出。",
            source=f"{SRC330_IO}; psc330_monitor_tool/psc330_monitor/app.py",
        )
    )


# PSC330 AI
ai330 = [
    (
        "AI0",
        "AI[0] / PressSensorAI0Disp / RoomPressureDisp",
        "房间压差",
        "500（换算）；902（最终控制/显示）",
        "904",
        "459",
        "499",
        "0-10V或4-20mA；电压上下限282/283，工程量上下限284/285",
        "Pa",
        "",
    ),
    (
        "AI1",
        "AI[1] / HumiditySensorAI1Disp",
        "房间/回风湿度",
        "501",
        "905",
        "460；432同步湿度输入方式",
        "498",
        "0-10V或4-20mA；湿度量程由温湿度传感器参数组换算",
        "0.1%RH",
        "与AI4受参数432同步选择影响",
    ),
    (
        "AI2",
        "AI[2] / CO2Disp",
        "CO2浓度",
        "903",
        "906",
        "461",
        "497",
        "0-10V或4-20mA；默认工程范围0～参数466（默认5000）",
        "ppm",
        "",
    ),
    (
        "AI3",
        "AI[3] / MainFanPaDisp / MainFanm3hDisp",
        "送风压力，或风量/风速复用输入",
        "1125（压力）；1126（风量/风速）",
        "907",
        "462",
        "496",
        "0-10V或4-20mA；压力范围282～285；风速/风量范围286～289",
        "Pa或0.1m/s等配置单位",
        "同一物理AI同时计算压力值和风量/风速值，控制功能按配置取用",
    ),
    (
        "AI4",
        "AI[4] / FreshAirHumidityDisp",
        "新风湿度",
        "519",
        "908",
        "463；432同步湿度输入方式",
        "457",
        "0-10V或4-20mA；湿度量程由温湿度传感器参数组换算",
        "0.1%RH",
        "与AI1受参数432同步选择影响",
    ),
]
for point, variable, function, eng, raw, config, calibration, signal, unit, reuse in ai330:
    rows.append(
        row(
            "PSC330",
            "AI",
            point,
            variable,
            function,
            local_address=eng,
            raw_address=raw,
            config_address=config,
            calibration=calibration,
            signal=signal,
            unit=unit,
            access="原始/工程值RO；类型和校准RW",
            reuse=reuse,
            note="类型0=0-10V，类型1=4-20mA；当前固件默认类型为0-10V。原始值约按0.01V表示，400约为4.00V。",
            source=f"{SRC330_USER}; {SRC330_ACTION}",
        )
    )


# PSC330 NTC
ntc330 = [
    ("NTC0", "AI[5] / RoomTempAI20 / RoomTempAI11Disp", "房间/回风温度", 511, 1374, 495),
    ("NTC1", "AI[6] / SupplyAirTempNTC / SysOutTempAI10Disp", "送风温度", 510, 1375, 494),
    ("NTC2", "AI[7] / FreshAirTempDisp", "新风温度", 512, 1376, 493),
    ("NTC3", "AI[8] / PreheatAfterTempDisp", "预热后温度", 513, 1377, 492),
    ("NTC4", "AI[9] / CompEva1_4 / CompEva14Disp", "A-1蒸发温度", 515, 1378, 491),
    ("NTC5", "AI[10] / CompEva1_5 / CompEva15Disp", "A-2蒸发温度", 516, 1379, 490),
    ("NTC6", "AI[11] / EvapTempB1Disp", "B-1蒸发温度", 514, 1380, 489),
    ("NTC7", "AI[12] / EvapTempB2Disp", "B-2蒸发温度", 517, 1381, 488),
    ("NTC8", "AI[13] / EvapTempC1Disp", "C-1蒸发温度", 520, 1382, 487),
    ("NTC9", "AI[14] / EvapTempC2Disp", "C-2蒸发温度", 521, 1383, 486),
    ("NTC10", "AI[15] / EvapTempD1Disp", "D-1蒸发温度", 522, 1384, 485),
    ("NTC11", "AI[16] / EvapTempD2Disp", "D-2蒸发温度", 523, 1385, 484),
]
for point, variable, function, eng, raw, calibration in ntc330:
    rows.append(
        row(
            "PSC330",
            "NTC",
            point,
            variable,
            function,
            local_address=str(eng),
            raw_address=str(raw),
            calibration=str(calibration),
            signal="NTC温度探头，经ADS1115和阻值表换算",
            unit="0.1℃",
            access="原始/工程值RO；校准RW",
            note="原始ADS1115码为0或接近32760时判无效；无效工程值通常为9999。校准范围由固件限制。",
            source=f"{SRC330_USER}; {SRC330_NTC}",
        )
    )


# PSC330 AO
ao330 = [
    ("DA0", "DA[0]", "再热/辅热/主制热或SCR第1组", "914；兼容显示506", "332、450、451", "1:1:1 SCR的0～40%区段", ""),
    ("DA1", "DA[1]", "预热/共享加热或SCR第2组", "915；兼容显示507", "333、452", "1:1:1 SCR的40～70%区段", ""),
    ("DA2", "DA[2]", "加湿器模拟量输出", "916", "334", "", ""),
    ("DA3", "DA[3]", "新风阀模拟量输出", "917", "335", "", ""),
    ("DA4", "DA[4]", "回风机或回风阀模拟量输出", "918", "330、337、449", "回风机与回风阀共用DA4，配置必须互斥", ""),
    ("DA5", "DA[5]", "混风阀模拟量输出", "919", "由风阀控制配置决定", "", ""),
    ("DA6", "DA[6]", "排风阀模拟量输出", "920", "338", "AO排风阀要求相关新风阀/CO2/焓差配置合法", ""),
    ("DA7", "DA[7]", "送风机或送风阀模拟量输出", "921；送风机控制值1124", "307、329、336、339～342", "送风机与送风阀共用DA7，配置必须互斥", ""),
    ("DA8", "DA[8]", "冷水阀模拟量输出", "922（目标）；925（实际）", "由冷水阀/制冷执行器配置决定", "", "现场判断优先读取925实际输出"),
    ("DA9", "DA[9]", "加热/SCR第3组", "923", "332、333、450～452", "1:1:1 SCR的70～100%区段；与DA0/DA1成组", ""),
]
for point, variable, function, eng, config, reuse, note in ao330:
    rows.append(
        row(
            "PSC330",
            "AO",
            point,
            variable,
            function,
            local_address=eng,
            config_address=config,
            signal="0～1000对应0～10V",
            unit="0.01V（显示值/100）",
            access="RO（最终输出监视）；配置RW",
            reuse=reuse,
            note=note,
            source=f"PSC330RK-V10-内机/User/wellthinker/inc/dac.h; {SRC330_ACTION}; psc330_monitor_tool/psc330_monitor/app.py",
        )
    )


# PSC316 DI and DO are packed into Parameter[1470].
di316 = [
    ("X00", "X00 / Comp1HightOverX06", "1#压缩机高压开关"),
    ("X01", "X01 / Comp1LowX01", "1#压缩机低压开关"),
    ("X02", "X02 / Comp2HightOverX10", "2#压缩机高压开关"),
    ("X03", "X03 / Comp2LowX03", "2#压缩机低压开关"),
    ("X04", "X04 / Fan1OverX12", "1#冷凝风机过载"),
    ("X05", "X05 / Fan2OverX17", "2#冷凝风机过载"),
    ("X06", "X06 / Comp1OverX06", "1#压缩机过载"),
    ("X07", "X07 / Comp2OverX07", "2#压缩机过载"),
]
for index, (point, variable, function) in enumerate(di316):
    rows.append(
        row(
            "PSC316",
            "DI",
            point,
            variable,
            function,
            local_address="1470（XY状态字）",
            bit=f"bit{index}",
            gateway=gateway_addresses(50),
            config_address=str(2 + index),
            signal="开关量；极性参数为1时使用原值，为0时逻辑取反",
            access="状态RO；极性RW",
            note="固件约300ms确认后形成Xxx_En故障输入；330镜像地址按1～4号外机顺序列出。",
            source=f"{SRC316_IO}; {SRC316_USER}; PSC316RK-V12-外机/WELLTHINKER/User/user.c",
        )
    )

do316 = [
    ("Y00", "Y00 / Comp1Y05", "1#压缩机继电器"),
    ("Y01", "Y01 / Comp2Y06", "2#压缩机继电器"),
    ("Y02", "Y02 / Fan1Y03", "风机1/定速风机/变频风机使能"),
    ("Y03", "Y03 / Fan3Y07", "风机2/低速/辅助定速风机"),
    ("Y04", "Y04 / Four1Y02", "1#四通阀"),
    ("Y05", "Y05 / Four2Y03", "2#四通阀"),
    ("Y06", "Y06 / Under1Y13", "压缩机曲轴箱加热带"),
    ("Y07", "Y07 / WaHeaterY07", "双速风机高速接触器"),
]
for index, (point, variable, function) in enumerate(do316):
    rows.append(
        row(
            "PSC316",
            "DO",
            point,
            variable,
            function,
            local_address="1470（XY状态字）",
            bit=f"bit{8 + index}",
            gateway=gateway_addresses(50),
            signal="继电器/开关量输出；0=断开，1=吸合",
            access="RO（状态监视）",
            reuse="Y02/Y03/Y07的具体风机作用随外机环境型号和冷凝风机型号配置变化。" if point in {"Y02", "Y03", "Y07"} else "",
            note="同一个1470状态字同时包含DI bit0～7和DO bit8～15。",
            source=f"{SRC316_IO}; {SRC316_USER}; {SRC316_ACTION}",
        )
    )


# PSC316 pressure AI
ai316 = [
    ("AI0", "AI[0] / HighPressDisp1", "1#高压传感器", 1443, 23, "", 499, "高压量程参数52"),
    ("AI1", "AI[1] / HighPressDisp2", "2#高压传感器", 1445, 25, "", 498, "高压量程参数52"),
    ("AI2", "AI[2] / LowPressure / LowPressDisp1", "1#低压传感器", 1444, 24, "730", 497, "低压量程参数51；当前代码强制2000kPa"),
    ("AI3", "AI[3] / LowPressure2 / LowPressDisp2", "2#低压传感器", 1446, 26, "732", 496, "低压量程参数51；当前代码强制2000kPa"),
]
for point, variable, function, local, gateway_offset, raw_addr, calibration, range_note in ai316:
    rows.append(
        row(
            "PSC316",
            "AI",
            point,
            variable,
            function,
            local_address=str(local),
            gateway=gateway_addresses(gateway_offset),
            raw_address=raw_addr or "当前源码未提供独立Modbus原始诊断地址",
            config_address="107（压力传感器配置）；468～471为AI通道选择/兼容配置",
            calibration=str(calibration),
            signal=f"当前换算按0.5～4.5V压力传感器标度；源码内部采样端点400～2000；{range_note}",
            unit="kPa",
            access="工程值RO；配置和校准RW",
            note="AI4、AI5属于ADC数组/硬件兼容槽位，当前业务代码未作为现场测量点使用，故不列为现场AI。",
            source=f"{SRC316_USER}; {SRC316_ACTION}",
        )
    )


# PSC316 NTC
ntc316 = [
    ("NTC0", "AI[6] / EnviTempAI0 / EnviTempAI0Disp", "环境温度", 1422, 2, 493),
    ("NTC1", "AI[7] / FinTemp1AI5 / FinTemp1AI5Disp", "1#翅片温度", 1431, 11, 492),
    ("NTC2", "AI[8] / FinTemp2AI6 / FinTemp2AI7Disp", "2#翅片温度", 1432, 12, 491),
    ("NTC3", "AI[9] / CompExhaustAI12 / CompExhaustAI12Disp", "1#排气温度", 1433, 13, 490),
    ("NTC4", "AI[10] / CompExhaustAI13 / CompExhaustAI13Disp", "2#排气温度", 1434, 14, 489),
    ("NTC5", "AI[11] / SuctionTempAI16 / MainTempAI16Disp", "1#吸气温度", 1435, 15, 488),
    ("NTC6", "AI[12] / SuctionTempAI17 / MainTempAI17Disp", "2#吸气温度", 1436, 16, 487),
    ("NTC7", "AI[13] / SlaveTempAI20Disp", "阀后温度1/备用温度", 1423, 3, 486),
]
for point, variable, function, local, gateway_offset, calibration in ntc316:
    rows.append(
        row(
            "PSC316",
            "NTC",
            point,
            variable,
            function,
            local_address=str(local),
            gateway=gateway_addresses(gateway_offset),
            calibration=str(calibration),
            signal="NTC温度探头，经ADS1115和阻值表换算",
            unit="0.1℃",
            access="工程值RO；校准RW",
            note="NTC校准实际公式为Parameter[493-i]，因此NTC0～NTC7对应493～486。1424/网关base+4为阀后温度2占位，固定9999，无第9路物理NTC。",
            source=f"{SRC316_NTC}; {SRC316_ACTION}",
        )
    )


# PSC316 AO
ao316 = [
    ("DA0", "DA[0] / DA0value / DA0ValueDisp", "冷凝风机模拟量输出", 1468, 48, "风机类型参数166；最高/最低频率等参数"),
    ("DA1", "DA[1] / DA1value / DA1ValueDisp", "第二冷凝风机模拟量/备用输出", 1469, 49, "风机类型参数166；最高/最低频率等参数"),
]
for point, variable, function, local, gateway_offset, config in ao316:
    rows.append(
        row(
            "PSC316",
            "AO",
            point,
            variable,
            function,
            local_address=str(local),
            gateway=gateway_addresses(gateway_offset),
            config_address=config,
            signal="0～1000对应0～10V",
            unit="0.01V（显示值/100）",
            access="RO（输出监视）；配置RW",
            reuse="DA0在风机类型2或4时用于变频风机；DA1会随部分双风机旧逻辑输出，具体作用取决于风机配置。",
            note="EEV驱动中的PWM/步进脉冲不属于现场0～10V AO，不计入AO数量。",
            source=f"PSC316RK-V12-外机/SYSTEM/inc/dac.h; {SRC316_ACTION}",
        )
    )


for index, item in enumerate(rows, start=1):
    item["序号"] = str(index)


def write_csv() -> None:
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def style_sheet(ws) -> None:
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="D9E2F3")
    category_fills = {
        "DI": PatternFill("solid", fgColor="E2F0D9"),
        "DO": PatternFill("solid", fgColor="FCE4D6"),
        "AI": PatternFill("solid", fgColor="DDEBF7"),
        "AO": PatternFill("solid", fgColor="FFF2CC"),
        "NTC": PatternFill("solid", fgColor="E4DFEC"),
    }
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row_cells in ws.iter_rows(min_row=2):
        category = row_cells[2].value
        fill = category_fills.get(category)
        for cell in row_cells:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)
        if fill:
            row_cells[2].fill = fill
            row_cells[2].font = Font(bold=True)
    widths = {
        1: 7,
        2: 11,
        3: 8,
        4: 11,
        5: 11,
        6: 34,
        7: 28,
        8: 26,
        9: 11,
        10: 31,
        11: 24,
        12: 25,
        13: 18,
        14: 48,
        15: 15,
        16: 22,
        17: 44,
        18: 52,
        19: 52,
    }
    for index, width in widths.items():
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 34


def append_table(ws, data: list[dict[str, str]]) -> None:
    ws.append(HEADERS)
    for item in data:
        ws.append([item[header] for header in HEADERS])
    style_sheet(ws)


def write_xlsx() -> None:
    wb = Workbook()
    wb.remove(wb.active)

    append_table(wb.create_sheet("总表"), rows)
    append_table(
        wb.create_sheet("PSC330_DI_DO"),
        [item for item in rows if item["板卡"] == "PSC330" and item["类别"] in {"DI", "DO"}],
    )
    append_table(
        wb.create_sheet("PSC330_AI_NTC_AO"),
        [item for item in rows if item["板卡"] == "PSC330" and item["类别"] in {"AI", "NTC", "AO"}],
    )
    append_table(
        wb.create_sheet("PSC316_DI_DO"),
        [item for item in rows if item["板卡"] == "PSC316" and item["类别"] in {"DI", "DO"}],
    )
    append_table(
        wb.create_sheet("PSC316_AI_NTC_AO"),
        [item for item in rows if item["板卡"] == "PSC316" and item["类别"] in {"AI", "NTC", "AO"}],
    )

    ws = wb.create_sheet("地址说明")
    notes = [
        ("生成日期", date(2026, 9, 7).isoformat()),
        ("地址基准", "表内Modbus地址按源码Parameter[]的0基地址填写。MCGS若设备驱动采用40001基准显示，应按驱动规则换算。"),
        ("PSC330数量", "14 DI + 16 DO + 5 AI + 12 NTC + 10 AO = 57个物理点；另列X16/X17两个逻辑预留显示位。"),
        ("PSC316数量", "8 DI + 8 DO + 4压力AI + 8 NTC + 2 AO = 30个物理点。"),
        ("316状态镜像基址", "1～4号外机分别为1550、1620、1690、1760，每台步长70。"),
        ("316 DI/DO", "本机Parameter[1470]为XY状态字；bit0～7是X00～X07，bit8～15是Y00～Y07。"),
        ("316网关DI/DO", "1～4号外机XY状态字镜像分别为1600、1670、1740、1810。"),
        ("316参数网关", "330端外机参数写入区从1830开始，每台步长48；它不是本表中状态/工程值镜像区。"),
        ("AI类型", "PSC330类型0=0-10V，类型1=4-20mA；当前默认0-10V。PSC316压力当前按0.5～4.5V标度。"),
        ("AO标度", "PSC330和PSC316现场AO显示值0～1000对应0～10V。"),
        ("NTC无效值", "温度工程值9999通常表示探头开路、短路、超表或采样无效。"),
        ("MCU引脚", "当前工程未包含IO底层驱动实现源码，仅有io.h接口，因此不能从当前源码可靠导出MCU GPIO管脚；物理接线以X/Y/AI/AO/NTC端子号为准。"),
        ("316占位温度", "PSC316本机1424及网关base+4为阀后温度2占位，当前固定9999，不是物理NTC。"),
        ("EEV说明", "PSC316的EEV由步进/PWM脉冲驱动，不属于现场0～10V AO，未计入AO点数。"),
    ]
    ws.append(["项目", "说明"])
    for item in notes:
        ws.append(item)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 115
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center")
    for row_cells in ws.iter_rows(min_row=2):
        for cell in row_cells:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    wb.save(XLSX_PATH)


def markdown_table(data: list[dict[str, str]], columns: list[str]) -> str:
    def clean(value: str) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for item in data:
        lines.append("| " + " | ".join(clean(item[column]) for column in columns) + " |")
    return "\n".join(lines)


def write_markdown() -> None:
    counts: dict[tuple[str, str], int] = {}
    for item in rows:
        key = (item["板卡"], item["类别"])
        counts[key] = counts.get(key, 0) + 1

    columns = [
        "板卡",
        "类别",
        "物理点位",
        "功能",
        "本机Modbus状态/工程值地址",
        "330网关镜像地址（1～4号外机）",
        "配置/极性地址",
        "校准参数地址",
        "信号类型/量程",
        "备注",
    ]
    content = f"""# PSC330/PSC316 IO点位说明

生成日期：2026-09-07

## 数量

- PSC330：14 DI、16 DO、5 AI、12 NTC、10 AO，共57个物理点；另有X16/X17两个逻辑预留显示位。
- PSC316：8 DI、8 DO、4压力AI、8 NTC、2 AO，共30个物理点。
- 总表：{len(rows)}行，其中87个物理点、2个逻辑预留点。

## 关键说明

- 表内Modbus地址按源码 `Parameter[]` 的0基地址填写。MCGS是否显示为40001基准，取决于设备驱动设置。
- PSC316的1～4号外机状态镜像基址分别是1550、1620、1690、1760，每台步长70。
- PSC316的DI/DO在本机1470状态字中：bit0～7为X00～X07，bit8～15为Y00～Y07。
- PSC330 AI输入类型：0为0-10V，1为4-20mA；当前固件默认0-10V。
- PSC316压力输入当前按0.5～4.5V传感器标度换算。
- AO显示值0～1000对应0～10V。
- 当前工程没有IO底层驱动实现源码，无法可靠导出MCU GPIO管脚；本表以板上X/Y/AI/AO/NTC端子为物理点位。
- PSC316的EEV是步进/PWM驱动，不属于现场0～10V AO。

## PSC330 DI/DO

{markdown_table([item for item in rows if item["板卡"] == "PSC330" and item["类别"] in {"DI", "DO"}], columns)}

## PSC330 AI/NTC/AO

{markdown_table([item for item in rows if item["板卡"] == "PSC330" and item["类别"] in {"AI", "NTC", "AO"}], columns)}

## PSC316 DI/DO

{markdown_table([item for item in rows if item["板卡"] == "PSC316" and item["类别"] in {"DI", "DO"}], columns)}

## PSC316 AI/NTC/AO

{markdown_table([item for item in rows if item["板卡"] == "PSC316" and item["类别"] in {"AI", "NTC", "AO"}], columns)}
"""
    MD_PATH.write_text(content, encoding="utf-8")


def verify() -> None:
    expected = {
        ("PSC330", "DI"): 16,
        ("PSC330", "DO"): 16,
        ("PSC330", "AI"): 5,
        ("PSC330", "NTC"): 12,
        ("PSC330", "AO"): 10,
        ("PSC316", "DI"): 8,
        ("PSC316", "DO"): 8,
        ("PSC316", "AI"): 4,
        ("PSC316", "NTC"): 8,
        ("PSC316", "AO"): 2,
    }
    actual: dict[tuple[str, str], int] = {}
    for item in rows:
        key = (item["板卡"], item["类别"])
        actual[key] = actual.get(key, 0) + 1
    if actual != expected:
        raise RuntimeError(f"点位数量不符: {actual!r}")
    if len(rows) != 89:
        raise RuntimeError(f"总点位行数应为89，实际{len(rows)}")

    wb = load_workbook(XLSX_PATH, read_only=True, data_only=True)
    expected_sheets = {
        "总表",
        "PSC330_DI_DO",
        "PSC330_AI_NTC_AO",
        "PSC316_DI_DO",
        "PSC316_AI_NTC_AO",
        "地址说明",
    }
    if set(wb.sheetnames) != expected_sheets:
        raise RuntimeError(f"工作表不符: {wb.sheetnames!r}")
    if wb["总表"].max_row != 90:
        raise RuntimeError(f"Excel总表行数错误: {wb['总表'].max_row}")
    wb.close()

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    if len(csv_rows) != 89:
        raise RuntimeError(f"CSV行数错误: {len(csv_rows)}")

    for path in (XLSX_PATH, CSV_PATH, MD_PATH):
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError(f"输出文件无效: {path}")


def write_and_verify_zip() -> None:
    with ZipFile(ZIP_PATH, "w", compression=ZIP_DEFLATED) as archive:
        for path in (XLSX_PATH, CSV_PATH, MD_PATH):
            archive.write(path, arcname=path.name)

    with ZipFile(ZIP_PATH, "r") as archive:
        expected_names = {XLSX_PATH.name, CSV_PATH.name, MD_PATH.name}
        if set(archive.namelist()) != expected_names:
            raise RuntimeError(f"ZIP文件清单错误: {archive.namelist()!r}")
        for name in expected_names:
            if archive.getinfo(name).file_size == 0:
                raise RuntimeError(f"ZIP内文件为空: {name}")


def main() -> None:
    write_csv()
    write_xlsx()
    write_markdown()
    verify()
    write_and_verify_zip()
    print(f"生成完成: {XLSX_PATH}")
    print(f"生成完成: {CSV_PATH}")
    print(f"生成完成: {MD_PATH}")
    print(f"生成完成: {ZIP_PATH}")
    print("校验完成: 89行点位，87个物理点，2个逻辑预留点")


if __name__ == "__main__":
    main()
