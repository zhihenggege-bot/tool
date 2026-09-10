# PSC330 接 HMI 读写地址逐点表

> 适用对象：PSC330RK-V10 内机，HMI/Modbus Poll 直接读写 PSC330 的 `Parameter[]` 和 `Pcoil[]`。
>
> 重要约定：本文地址均按代码里的 `Parameter[N]` / `Pcoil[N]` 写，使用 Modbus Poll 时，协议地址填 `N`。本工程串口 1 Modbus 代码没有对地址做 `+1` 偏移。

## 1. Modbus Poll 地址规则

| 功能 | 功能码 | 地址对象 | 说明 |
|---|---:|---|---|
| 读参数寄存器 | 03 | Parameter[N] | 协议地址直接填 N |
| 写单个参数 | 06 | Parameter[N] | 受写保护和 min/max 限制 |
| 写多个参数 | 16 | Parameter[N] | 连续写，任一地址非法则本帧丢弃 |
| 读线圈 | 01 | Pcoil[N] | 线圈/故障位 |
| 写线圈 | 05 | Pcoil[N] | 只开放 4/5/6/50/51/128 |

地址自检：读 465 应为 1200，466 应为 5000，467 应为 3300。若整体错一位，先关掉 Modbus Poll 的 4x 引用地址显示。

## 2. 读写权限总表

| 地址范围 | HMI权限 | 含义 |
|---:|---|---|
| 0~449 | RW | 保存参数，受 Parameter_min/max 限制 |
| 450~458 | RO(隐藏) | AI/NTC校准及工厂隐藏区 |
| 459~463 | RW | AI0~AI4 0-10V/4-20mA 类型选择，现场必须能写 |
| 464~499 | RO(隐藏) | AI/NTC校准及工厂隐藏区，A5不是普通AI |
| 500~1299 | RO | 运行显示、状态、报警；其中 524 SysErrorReset 允许 HMI 写 0/1 做本机故障复位 |
| 1300~1309 | 条件RW | 手动调试，需 SysStep=0 且 HandDebug=1 |
| 1400~1411 | 条件RW/受限 | PLC控制区，仅1402复位、1406急停允许写0/1 |
| 1420~1495 | RO | 模块/外机读回状态镜像 |
| 1550~1829 | RO | 1~4#模块 PLCMonitor 镜像 |
| 1830~1997 | RW/RO | PSC316外机网关区，每台42点，0~32可写设定，33~40只读诊断，41为316变频器类型CompChoice可读写 |
| 1998~1999 | 保留 | 不建议HMI使用 |

## 3. AI / NTC 固定分配

| 通道 | 功能 | 类型 | 主要寄存器 |
|---|---|---|---|
| AI0 | 房间压差 | 0-10V/4-20mA，459选择 | 500, 902, 904 |
| AI1 | 房间湿度 | 0-10V/4-20mA，460或432选择 | 501, 905 |
| AI2 | CO2 | 0-10V/4-20mA，461选择 | 903, 906 |
| AI3 | 送风压力/风速 | 0-10V/4-20mA，462选择 | 1125, 1126, 907 |
| AI4 | 新风湿度 | 0-10V/4-20mA，463或432选择 | 519, 908 |
| NTC0 | 房间/回风温度 | NTC | 511 |
| NTC1 | 送风温度 | NTC | 510 |
| NTC2 | 新风温度 | NTC | 512 |
| NTC3 | 预热后温度 | NTC | 513 |
| NTC4~NTC11 | A-1/A-2/B-1/B-2/C-1/C-2/D-1/D-2蒸发温度 | NTC | 515,516,514,517,520,521,522,523 |

## 4. 报警怎么看

当前故障不要看 703，703 是累计故障次数。现场看 630/631/632 三个故障字，建议 HMI 按 uint16 或 HEX 显示。单点故障看 594~647。复位本机故障写 524=1；如果传感器/联锁仍异常，会马上再次报警。704 不是复位地址，704 是最大可用压缩机数显示。

| 故障字 | 位定义 |
|---:|---|
| 630 | bit0~15 对应 594~609 |
| 631 | bit0~14 对应 610~624 |
| 632 | bit0=AI0，bit1~4=C1/C2/D1/D2蒸发温度，bit5~8=C1/C2/D1/D2蒸发低温保护 |

### 4.1 外机数量设置

现场用 `388 OutdoorUnitNumSet` 设置外机板数量，不要直接写 `214 ModuleNumSet`。

| 388值 | 启用系统 | 需要接的蒸发温度 | 自动内部值 |
|---:|---|---|---:|
| 1 | A系统 | NTC4=A-1，NTC5=A-2 | 214=2 |
| 2 | A/B系统 | 加上 NTC6=B-1，NTC7=B-2 | 214=3 |
| 3 | A/B/C系统 | 加上 NTC8=C-1，NTC9=C-2 | 214=4 |
| 4 | A/B/C/D系统 | 加上 NTC10=D-1，NTC11=D-2 | 214=5 |

当 `388=1` 时，B/C/D 未接的 NTC6~NTC11 不再产生 614/615/623/624/625/626 传感器故障，也不再触发 B/C/D 蒸发低温保护。

### 4.2 现场容易误判的几个地址

| 地址 | 真实用途 | 现场说明 |
|---:|---|---|
| 1 | `UserWorkModeSet` 实际主控模式 | 范围是 0~2：0制冷，1制热，2通风。消毒/排毒/自动不要写 1，要写 236。 |
| 236 | `UserWorkModeSetTEMP` 完整用户模式 | 0制冷，1制热，2通风，3消毒，4排毒，5自动。代码会由 236 归一化到 1。 |
| 155~159 | X00~X04 输入极性选择 | 0=取反，1=不取反；用来适配常闭/常开接线，不是报警状态。 |
| 389~397 | X05~X15 输入极性选择 | 0=取反，1=不取反；对应 X05/X06/X07/X10/X11/X12/X13/X14/X15。 |
| 167 | `SysRunHour` 系统累计运行小时 | 每小时累加到 30000；维护提醒和试用到期会用它。 |
| 214 | `ModuleNumSet` 内部模块总数 | 不建议 HMI 直接写；现在由 388 自动换算，值=外机数量+1。 |
| 388 | `OutdoorUnitNumSet` 外机板数量 | 1=A，2=A/B，3=A/B/C，4=A/B/C/D。现场只有一块外机板就写 1。 |
| 510~523 | NTC/部分状态显示区 | 地址顺序是历史遗留宏名，不按 NTC0、NTC1、NTC2 顺序排列；以本文“含义”列和 AI/NTC 固定分配为准。 |
| 600 | `TSysOutTempErr` | 主要是 NTC2 新风温度故障，但代码也会在加湿器故障或房间湿度故障时复用置 1。 |
| 605 | `EnviTempErr` | 综合联锁/保护故障：火警、风阀联锁、漏水、排风/回风过载、加热故障、预热故障、X0电源/相序/急停等都会置 1。 |
| 1350~1365 | `X00InputDisp`~`X17InputDisp` | DI 诊断显示区，HMI 连续读 16 个寄存器即可看输入状态；V10 实际硬件只有 X00~X07、X10~X15，X16/X17 固定 0。 |

### 4.3 HMI 开机步骤

开机前先确认：`710 SysErrStatus=0`，`700 SysStatus` 不是 2，`709 SysStep=0`。如果仍有故障，先处理 `594~647` 和 `1350~1363`，然后按 `524=1 -> 524=0` 复位。

HMI/Modbus Poll 推荐用本地命令开机：

| 步骤 | 写入/读取 | 说明 |
|---:|---|---|
| 1 | 写 `163=0` | 选择本地/HMI 开停机来源 |
| 2 | 写 `398=1` | 开机命令 |
| 3 | 读 `700` | 正常应从 0 变 4，或预热时显示预热开机状态 |
| 4 | 读 `709` | 开机时序会从 0 进入 1，最终到 2 表示运行中 |
| 5 | 写 `398=0` | 关机命令 |

不要再用 `521` 做开关机。`521` 在当前表里用于 NTC9 C-2 蒸发温度显示，历史宏名曾复用 `TouchScreenONOFF`，继续用会和温度显示冲突。
## 5. 完整逐寄存器表（Parameter[0]~Parameter[1999]）

说明：0~499 的“范围/默认”来自 `Parameter_min/max/def`，并叠加 `ParameterInit()` 里的覆盖值；500 以后的运行值没有固定默认。乱码历史注释不作为中文含义来源，表内中文含义按宏名、代码用途和已核对规格书整理。

### 0~199

| 地址 | 变量/宏 | 权限 | 范围 | 默认 | 含义 |
|---:|---|---|---:|---:|---|
| 0 | - | RW | -1000..32767 | 0 | 系统保留/板地址相关，普通HMI不要写 |
| 1 | UserWorkModeSet | RW | 0..2 | 0 | 主控工作模式：0制冷，1制热，2通风；3/4/5 不写这里，完整用户模式写236 |
| 2 | InPutStatusSet0 | RW | 0..1 | 0 | DI/输入状态设置0，历史系统参数 |
| 3 | InPutStatusSet1 | RW | 0..1 | 0 | DI/输入状态设置1，历史系统参数 |
| 4 | InPutStatusSet2 | RW | 0..1 | 0 | DI/输入状态设置2，历史系统参数 |
| 5 | InPutStatusSet3 | RW | 0..1 | 0 | DI/输入状态设置3，历史系统参数 |
| 6 | InPutStatusSet4 | RW | 0..1 | 0 | DI/输入状态设置4，历史系统参数 |
| 7 | InPutStatusSet5 | RW | 0..1 | 0 | DI/输入状态设置5，历史系统参数 |
| 8 | InPutStatusSet6 | RW | 0..1 | 0 | DI/输入状态设置6，历史系统参数 |
| 9 | InPutStatusSet7 | RW | 0..1 | 0 | DI/输入状态设置7，历史系统参数 |
| 10 | MotorTotalPulseSet | RW | 0..9999 | 500 | 电子膨胀阀总脉冲数 |
| 11 | EEVCloseMinSizeSet | RW | 0..999 | 48 | 电子膨胀阀最小关闭步数 |
| 12 | EEVOpenMaxSizeSet | RW | 0..999 | 500 | 电子膨胀阀最大开度步数 |
| 13 | EEVTempDev1Set | RW | 0..99 | 5 | EEV温差偏差1 |
| 14 | EEVTempDev2Set | RW | 0..99 | 10 | EEV温差偏差2 |
| 15 | EEVTempDev3Set | RW | 0..99 | 20 | EEV温差偏差3 |
| 16 | EEVAdjustTimeSet1 | RW | 0..999 | 60 | EEV调节时间1 |
| 17 | EEVAdjustTimeSet2 | RW | 0..999 | 30 | EEV调节时间2 |
| 18 | EEVAdjustTimeSet3 | RW | 0..999 | 2 | EEV调节时间3 |
| 19 | EEVInitialSizeDlySet | RW | 0..999 | 90 | EEV初始开度延时 |
| 20 | GetTempTimeSet | RW | 0..60 | 3 | 取温/采样周期 |
| 21 | DefrostEXVOpenSizeSet | RW | 0..999 | 50 | 化霜时EEV开度 |
| 22 | EEVInitialSizeSet1 | RW | 0..999 | 100 | 低温初始EEV开度1 |
| 23 | EEVInitialSizeSet4 | RW | 0..999 | 650 | 中温初始EEV开度4 |
| 24 | EEVInitialSizeSet6 | RW | 0..999 | 700 | 高温初始EEV开度6 |
| 25 | GErrCheckSet | RW | 1..255 | 2 | 通用故障检测延时 |
| 26 | CoolLowCheckSet | RW | 1..255 | 3 | 制冷低压检测延时 |
| 27 | HeatLowCheckSet | RW | 1..255 | 60 | 制热低压检测延时 |
| 28 | ExhaustHightTempSet | RW | 1000..1250 | 1100 | 排气高温保护值 |
| 29 | ExhaustReturnTempSet | RW | 800..1000 | 900 | 排气高温恢复值 |
| 30 | UnderHeaterOnSet | RW | 0..9999 | 5 | 底部/曲轴箱加热开启时间 |
| 31 | FanWaTempSet | RW | -300..200 | 0 | 风机防冷风温度1 |
| 32 | FanWaTempSet2 | RW | -300..200 | -100 | 风机防冷风温度2 |
| 33 | PressureLow | RW | 0..1000 | 0 | 低压保护阈值 |
| 34 | PressureHigh | RW | 0..2000 | 2000 | 高压保护阈值 |
| 35 | Y12_ctrlTempSet | RW | -300..300 | 0 | Y12控制温度设定 |
| 36 | FanType | RW | 0..3 | 3 | 风机类型 |
| 37 | FanLimitHigh | RW | 0..9999 | 900 | 风机最高限制 |
| 38 | CompChoice | RW | 0..3 | 3 | 压缩机/变频器类型选择：0定频，1老蓝海华腾协议，2汇川，3施耐德ATV610 |
| 39 | RefrigerantSetP02 | RW | 0..5 | 3 | 冷媒类型参数 |
| 40 | MachineOilSet | RW | 0..99 | 24 | 油加热/曲轴箱加热周期 |
| 41 | FourValveLaySet | RW | 0..255 | 10 | 四通阀延时 |
| 42 | MinStopTimeSet | RW | 30..600 | 180 | 压缩机最小停机时间 |
| 43 | MinRunTimeSet | RW | 30..600 | 180 | 压缩机最小运行时间 |
| 44 | DefDelayCheckTime | RW | 30..600 | 90 | 化霜检测延时 |
| 45 | FanONLaySet | RW | 0..255 | 15 | 风机开机延时 |
| 46 | SuperheatSet1 | RW | -99..999 | 40 | 过热度设定1 |
| 47 | SuperheatSet2 | RW | -99..999 | 40 | 过热度设定2 |
| 48 | CompVVFMaxFreSet | RW | 0..200 | 90 | 变频压缩机最高频率 |
| 49 | CompVVFMinFreSet | RW | 0..200 | 30 | 变频压缩机最低频率 |
| 50 | PressRange | RW | 0..9999 | 2000 | 压力传感器量程 |
| 51 | LowPressRange | RW | 0..9999 | 2000 | 低压压力量程 |
| 52 | HighPressRange | RW | 0..9999 | 5000 | 高压压力量程 |
| 53 | LowPressProctect | RW | 0..9999 | 900 | 低压保护值 |
| 54 | LowPressWarn | RW | 0..9999 | 150 | 低压报警值 |
| 55 | HighPressureSet | RW | 0..9999 | 2300 | 高压设定值 |
| 56 | VVFHighPressWarn | RW | 0..9999 | 4000 | 变频高压报警值 |
| 57 | FanLimit | RW | 0..9999 | 300 | 风机最低转速限制 |
| 58 | DefChoiceSet | RW | 0..1 | 1 | 化霜选择 |
| 59 | DefCompOnLayTimeSet | RW | 0..255 | 7 | 首次化霜延时 |
| 60 | DefCompRunLayTimeSet | RW | 0..60 | 5 | 压缩机运行后化霜允许延时 |
| 61 | CanDefFanTempSet | RW | -100..100 | -20 | 允许化霜盘管温度 |
| 62 | DefEnviFanTempGap1Set | RW | 0..250 | 80 | 化霜环境/盘管温差1 |
| 63 | DefEnviFanTempGap2Set | RW | 0..250 | 30 | 化霜环境/盘管温差2 |
| 64 | CanDefEnviTempSet | RW | 0..250 | 70 | 允许化霜环境温度 |
| 65 | DefrostStart1_TempSet | RW | -100..250 | 0 | 化霜启动温度1 |
| 66 | DefrostStart2_TempSet | RW | -100..250 | -50 | 化霜启动温度2 |
| 67 | DefrostStart1_GapTimeSet | RW | 0..255 | 60 | 化霜间隔1 |
| 68 | DefrostStart2_GapTimeSet | RW | 0..255 | 45 | 化霜间隔2 |
| 69 | DefrostStart3_GapTimeSet | RW | 0..255 | 30 | 化霜间隔3 |
| 70 | DefrostTimeSet | RW | 60..1500 | 300 | 化霜最长时间 |
| 71 | EndDefWaterTempSet | RW | 0..250 | 40 | 退出化霜水温 |
| 72 | EndDefFanTempSet | RW | 0..350 | 280 | 退出化霜盘管温度 |
| 73 | DefLongWaitSet | RW | 0..255 | 10 | 化霜等待时间 |
| 74 | DefEnviFanTempGap3Set | RW | 0..250 | 80 | 化霜环境/盘管温差3 |
| 75 | DefrostStart3_TempSet | RW | -100..200 | 150 | 化霜启动温度3 |
| 76 | DefrostSnow_Set | RW | 0..1 | 0 | 雪天/强制化霜模式 |
| 77 | DefrostSnow_TIME | RW | 1..999 | 30 | 雪天化霜时间 |
| 78 | FourValveSet | RW | 0..1 | 1 | 四通阀系统配置 |
| 79 | FanTypeSet | RW | 0..1 | 1 | 风机系统配置 |
| 80 | EveNumSet | RW | -99..1 | 1 | 代码宏定义参数：EveNumSet |
| 81 | PLCAddress | RW | -99..255 | 1 | 代码宏定义参数：PLCAddress |
| 82 | DefrostCompSet | RW | 0..1 | 0 | 化霜相关参数 |
| 83 | FanValue1 | RW | 0..1000 | 500 | 风机相关参数/显示 |
| 84 | FanValue2 | RW | 0..1000 | 500 | 风机相关参数/显示 |
| 85 | FanValueDOWN | RW | 0..1000 | 200 | 风机相关参数/显示 |
| 86 | FanValueUP | RW | 0..1000 | 1000 | 风机相关参数/显示 |
| 87 | FanClosePressure | RW | 0..9999 | 1900 | 风机相关参数/显示 |
| 88 | FanOpenPressure | RW | 0..9999 | 2600 | 风机相关参数/显示 |
| 89 | SendtoModule | RW | 0..999 | 10 | 代码宏定义参数：SendtoModule |
| 90 | VVFTypeSet | RW | 0..9999 | 0 | 变频/频率相关显示或设定 |
| 91 | VF0 | RW | 0..999 | 0 | 代码宏定义参数：VF0 |
| 92 | ColdFanType | RW | 0..999 | 0 | 代码宏定义参数：ColdFanType |
| 93 | CompCouple | RW | 2..4 | 3 | 压缩机相关参数/显示 |
| 94 | MachineTypeSet | RW | 0..3 | 0 | 机型选择，恢复默认时保留，不建议现场随意修改 |
| 95 | CurrentHighSet | RW | 0..9999 | 300 | 30.0A 0-999.9A |
| 96 | ExhuastTempSet1 | RW | 0..1300 | 600 | 代码宏定义参数：ExhuastTempSet1 |
| 97 | ExvAdjExhTempDevSet | RW | -300..500 | 250 | 代码宏定义参数：ExvAdjExhTempDevSet |
| 98 | EEVOpenSizeSet5 | RW | 0..999 | 375 | 代码宏定义参数：EEVOpenSizeSet5 |
| 99 | Copheatfunction | RW | 0..1 | 1 | 代码宏定义参数：Copheatfunction |
| 100 | ColdEEV | RW | 0..1 | 1 | 代码宏定义参数：ColdEEV |
| 101 | ColdFan_Ctrl_Cycle | RW | 0..999 | 10 | 代码宏定义参数：ColdFan_Ctrl_Cycle |
| 102 | ColdFan_Ctrl_Step | RW | 0..1000 | 50 | 代码宏定义参数：ColdFan_Ctrl_Step |
| 103 | ColdFan_Ctrl_Div | RW | 0..9999 | 100 | 代码宏定义参数：ColdFan_Ctrl_Div |
| 104 | ColdFan_Ctrl_Div1 | RW | 0..9999 | 100 | 代码宏定义参数：ColdFan_Ctrl_Div1 |
| 105 | FanCouple1 | RW | 2..4 | 3 | 风机相关参数/显示 |
| 106 | VVFMotorSelect | RW | 0..1 | 0 | 变频/频率相关显示或设定 |
| 107 | PressSensor | RW | 0..2 | 0 | 全局外机压力传感器安装方式：0=无；1=高压+低压；2=仅低压。330 将 Parameter[81]~[107] 同步到全部 316；模式2保留低压保护和EEV PID，停用模拟高压，且禁止0~43°C、-15~43°C机型制冷 |
| 108 | SumHumidifier | RW | 0..1 | 1 | 代码宏定义参数：SumHumidifier |
| 109 | RemoveSet | RW | 0..999 | 0 | 代码宏定义参数：RemoveSet |
| 110 | DiskCheckSet | RW | -500..9999 | 15 | 代码宏定义参数：DiskCheckSet |
| 111 | DiskLowSet | RW | -500..9999 | -20 | 代码宏定义参数：DiskLowSet |
| 112 | DiskSet | RW | -500..9999 | 100 | 代码宏定义参数：DiskSet |
| 113 | ExTempSet | RW | -500..9999 | 950 | 代码宏定义参数：ExTempSet |
| 114 | - | RW | 0..250 | 80 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 115 | FinalChangeHMI | RW | -1000..1000 | 0 | 代码宏定义参数：FinalChangeHMI |
| 116 | EnergyAdjustFlag1 | RW | -1000..1000 | 0 | 代码宏定义参数：EnergyAdjustFlag1 |
| 117 | EnergyAdjustFlag2 | RW | -1000..1000 | 0 | 代码宏定义参数：EnergyAdjustFlag2 |
| 118 | CompNumSet | RW | 0..2 | 0 | 压缩机相关参数/显示 |
| 119 | CompNumCur | RW | 0..2 | 0 | 压缩机相关参数/显示 |
| 120 | RoomTempDiffSet | RW | 20..50 | 20 | 房间温差/死区设定，压缩机PID死区参与计算 |
| 121 | CompAdjustPara1 | RW | 0..1000 | 30 | 压缩机相关参数/显示 |
| 122 | CompAdjustPara2 | RW | 0..1000 | 300 | 压缩机相关参数/显示 |
| 123 | CompAdjustPara3 | RW | 0..1000 | 40 | 压缩机相关参数/显示 |
| 124 | CompAdjustPara4 | RW | 0..1000 | 280 | 压缩机相关参数/显示 |
| 125 | - | RW | 0..255 | 10 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 126 | - | RW | 0..250 | 80 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 127 | - | RW | -100..200 | 150 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 128 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 129 | - | RW | 1..999 | 30 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 130 | - | RW | 0..999 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 131 | - | RW | 0..999 | 50 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 132 | - | RW | 0..1300 | 700 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 133 | - | RW | 0..999 | 3 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 134 | - | RW | 0..999 | 100 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 135 | - | RW | 0..999 | 200 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 136 | - | RW | 0..999 | 375 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 137 | - | RW | 0..1300 | 800 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 138 | - | RW | -300..500 | 250 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 139 | - | RW | 0..1300 | 900 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 140 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 141 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 142 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 143 | - | RW | 0..255 | 1 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 144 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 145 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 146 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 147 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 148 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 149 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 150 | - | RW | 0..29999 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 151 | - | RW | 0..29999 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 152 | - | RW | 0..255 | 3 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 153 | - | RW | 0..255 | 60 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 154 | - | RW | 0..70 | 30 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 155 | InPutStatusSet8 | RW | 0..1 | 0 | X00 输入极性：0=取反，1=不取反；用于适配常闭/常开触点，不是报警状态 |
| 156 | InPutStatusSet9 | RW | 0..1 | 0 | X01 输入极性：0=取反，1=不取反；用于适配常闭/常开触点，不是报警状态 |
| 157 | InPutStatusSet10 | RW | 0..1 | 0 | X02 输入极性：0=取反，1=不取反；用于适配常闭/常开触点，不是报警状态 |
| 158 | InPutStatusSet11 | RW | 0..1 | 0 | X03 输入极性：0=取反，1=不取反；用于适配常闭/常开触点，不是报警状态 |
| 159 | InPutStatusSet12 | RW | 0..1 | 0 | X04 输入极性：0=取反，1=不取反；用于适配常闭/常开触点，不是报警状态 |
| 160 | UserColdTempSet | RW | 150..320 | 250 | 用户制冷温度设定，0.1C |
| 161 | UserHeatTempSet | RW | 150..800 | 450 | 用户制热温度设定，0.1C |
| 162 | HumiditySet | RW | 0..1000 | 400 | 湿度设定，0.1%RH |
| 163 | UserSwitchSet | RW | -300..2 | 0 | 用户开关选择/开停机命令来源 |
| 164 | UserAutoModeSet | RW | 0..1 | 0 | 自动模式相关设定 |
| 165 | UserWidsModeSet | RW | 0..1 | 0 | 代码宏定义参数：UserWidsModeSet |
| 166 | SysStatusLoader | RW | 0..1 | 0 | 代码宏定义参数：SysStatusLoader |
| 167 | SysRunHour | RW | 0..29999 | 0 | 系统累计运行小时；每小时累加到30000，维护提醒和试用到期逻辑会用到 |
| 168 | HumidtyHandle | RW | 0..1 | 0 | 加湿处理/加湿模式 |
| 169 | HumidtyValve | RW | 0..1 | 0 | 加湿阀手动/状态相关 |
| 170 | CompVVFDefAntFreSet | RW | 0..200 | 80 | 压缩机相关参数/显示 |
| 171 | CompVVFFreInitSet | RW | 0..200 | 45 | 压缩机相关参数/显示 |
| 172 | CompCurHPSet | RW | 100..999 | 350 | 压缩机相关参数/显示 |
| 173 | CompCurDevSet | RW | 0..200 | 10 | 压缩机相关参数/显示 |
| 174 | CompCurHPFrSet | RW | 1..50 | 1 | 压缩机相关参数/显示 |
| 175 | CompCurHPTmSet | RW | 1..999 | 5 | 压缩机相关参数/显示 |
| 176 | CompVVFSecondStart | RW | 0..200 | 70 | 压缩机相关参数/显示 |
| 177 | CompVVFTmInitSet | RW | 1..999 | 105 | 压缩机相关参数/显示 |
| 178 | VVFOilBackFre1 | RW | 101..150 | 101 | 变频/频率相关显示或设定 |
| 179 | VVFOilBackFre2 | RW | 60..100 | 80 | 变频/频率相关显示或设定 |
| 180 | VVFOilBackFre3 | RW | 0..49 | 40 | 变频/频率相关显示或设定 |
| 181 | VVFOilBackTime1 | RW | 0..999 | 120 | 变频/频率相关显示或设定 |
| 182 | VVFOilBackTime2 | RW | 0..999 | 120 | 变频/频率相关显示或设定 |
| 183 | VVFOilBackTime3 | RW | 0..999 | 120 | 变频/频率相关显示或设定 |
| 184 | OilTime | RW | 0..999 | 5 | 代码宏定义参数：OilTime |
| 185 | CompOilBackSet | RW | 0..200 | 60 | 压缩机相关参数/显示 |
| 186 | VVFHighPressHigh | RW | 0..9999 | 3800 | 变频/频率相关显示或设定 |
| 187 | VVFTempHigh | RW | 0..120 | 80 | 变频/频率相关显示或设定 |
| 188 | LowPressProctect2 | RW | 0..9999 | 300 | 代码宏定义参数：LowPressProctect2 |
| 189 | - | RW | 0..500 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 190 | UpLoadGap1Set | RW | 0..255 | 30 | 代码宏定义参数：UpLoadGap1Set |
| 191 | UpLoadGap2Set | RW | 0..255 | 10 | 代码宏定义参数：UpLoadGap2Set |
| 192 | UpLoadTime1Set | RW | 0..255 | 10 | 代码宏定义参数：UpLoadTime1Set |
| 193 | UpLoadTime2Set | RW | 0..255 | 20 | 代码宏定义参数：UpLoadTime2Set |
| 194 | DownLoadGap1Set | RW | 0..255 | 10 | 代码宏定义参数：DownLoadGap1Set |
| 195 | DownLoadGap2Set | RW | 0..255 | 20 | 代码宏定义参数：DownLoadGap2Set |
| 196 | DownLoadTime1Set | RW | 0..255 | 10 | 代码宏定义参数：DownLoadTime1Set |
| 197 | DownLoadTime2Set | RW | 0..255 | 5 | 代码宏定义参数：DownLoadTime2Set |
| 198 | - | RW | 0..999 | 3 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 199 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |

### 200~399

| 地址 | 变量/宏 | 权限 | 范围 | 默认 | 含义 |
|---:|---|---|---:|---:|---|
| 200 | WaterFlowErrorCheckSet | RW | 1..255 | 15 | 代码宏定义参数：WaterFlowErrorCheckSet |
| 201 | SysCoolOutLowSet | RW | -300..70 | 30 | 代码宏定义参数：SysCoolOutLowSet |
| 202 | SysHeatOutHighSet | RW | 400..800 | 550 | 代码宏定义参数：SysHeatOutHighSet |
| 203 | UserPumpPreSet | RW | 1..255 | 30 | 代码宏定义参数：UserPumpPreSet |
| 204 | PumpBeforeTimeSet | RW | 1..255 | 30 | 代码宏定义参数：PumpBeforeTimeSet |
| 205 | RecoverGapTempSet | RW | 0..100 | 30 | 代码宏定义参数：RecoverGapTempSet |
| 206 | FanValveDelay | RW | 0..999 | 150 | 风机相关参数/显示 |
| 207 | PreHeatControlSet | RW | -300..800 | 350 | 代码宏定义参数：PreHeatControlSet |
| 208 | - | RW | 0..90 | 3 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 209 | - | RW | 0..255 | 15 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 210 | AdjustPumpSet | RW | 0..1 | 0 | 代码宏定义参数：AdjustPumpSet |
| 211 | Y17OutSet | RW | 0..4 | 4 | 代码宏定义参数：Y17OutSet |
| 212 | ColdTempMinSet | RW | -300..500 | 0 | 代码宏定义参数：ColdTempMinSet |
| 213 | HeatTempMaxSet | RW | 0..800 | 500 | 代码宏定义参数：HeatTempMaxSet |
| 214 | ModuleNumSet | RW | 1..16 | 2 | 内部模块总数，自动等于 388+1；HMI现场不要直接写这个地址 |
| 215 | WaterWorkTypeSet | RW | 0..2 | 0 | 代码宏定义参数：WaterWorkTypeSet |
| 216 | InternalEEV | RW | 0..1 | 1 | 代码宏定义参数：InternalEEV |
| 217 | EEVChoice | RW | 0..1 | 0 | 代码宏定义参数：EEVChoice |
| 218 | UserRight3Set | RW | 0..30000 | 0 | 代码宏定义参数：UserRight3Set |
| 219 | DefrostFanSet | RW | 0..1 | 0 | 化霜相关参数 |
| 220 | EEVManuOpenSizeSet | RW | 0..999 | 0 | 代码宏定义参数：EEVManuOpenSizeSet |
| 221 | ManuCtrlEEVSet | RW | 0..1 | 0 | 代码宏定义参数：ManuCtrlEEVSet |
| 222 | EEV2ManuOpenSizeSet | RW | 0..999 | 0 | 代码宏定义参数：EEV2ManuOpenSizeSet |
| 223 | ManuCtrlEEV2Set | RW | 0..1 | 0 | 代码宏定义参数：ManuCtrlEEV2Set |
| 224 | EEV3ManuOpenSizeSet | RW | 0..999 | 0 | 代码宏定义参数：EEV3ManuOpenSizeSet |
| 225 | ManuCtrlEEV3Set | RW | 0..1 | 0 | 代码宏定义参数：ManuCtrlEEV3Set |
| 226 | EEV4ManuOpenSizeSet | RW | 0..999 | 0 | 代码宏定义参数：EEV4ManuOpenSizeSet |
| 227 | ManuCtrlEEV4Set | RW | 0..1 | 0 | 代码宏定义参数：ManuCtrlEEV4Set |
| 228 | EEV5ManuOpenSizeSet | RW | 0..999 | 0 | 代码宏定义参数：EEV5ManuOpenSizeSet |
| 229 | ManuCtrlEEV5Set | RW | 0..1 | 0 | 代码宏定义参数：ManuCtrlEEV5Set |
| 230 | EEV6ManuOpenSizeSet | RW | 0..999 | 0 | 代码宏定义参数：EEV6ManuOpenSizeSet |
| 231 | ManuCtrlEEV6Set | RW | 0..1 | 0 | 代码宏定义参数：ManuCtrlEEV6Set |
| 232 | EEV7ManuOpenSizeSet | RW | 0..999 | 0 | 代码宏定义参数：EEV7ManuOpenSizeSet |
| 233 | ManuCtrlEEV7Set | RW | 0..1 | 0 | 代码宏定义参数：ManuCtrlEEV7Set |
| 234 | EEV8ManuOpenSizeSet | RW | 0..999 | 0 | 代码宏定义参数：EEV8ManuOpenSizeSet |
| 235 | ManuCtrlEEV8Set | RW | -1..100 | 0 | 代码宏定义参数：ManuCtrlEEV8Set |
| 236 | UserWorkModeSetTEMP | RW | 0..5 | 0 | UserWorkModeSetTEMP，统一后的临时/内部工作模式：0制冷，1制热，2通风，3消毒，4排毒，5自动 |
| 237 | HeatCycleTime | RW | 0..1000 | 30 | 代码宏定义参数：HeatCycleTime |
| 238 | HeatLoadSet | RW | 0..100 | 5 | 代码宏定义参数：HeatLoadSet |
| 239 | HeatLimitOutput | RW | -1000..32767 | 1000 | 代码宏定义参数：HeatLimitOutput |
| 240 | HeatNumber | RW | -1000..32767 | 3 | 代码宏定义参数：HeatNumber |
| 241 | HumLoadvaleSet | RW | -1000..32767 | 50 | 代码宏定义参数：HumLoadvaleSet |
| 242 | HumLoadTimeSet | RW | -1000..32767 | 5 | 代码宏定义参数：HumLoadTimeSet |
| 243 | WorkMachineMode | RW | -1000..32767 | 0 | 代码宏定义参数：WorkMachineMode |
| 244 | HeatTempDown | RW | -1000..32767 | 5 | 代码宏定义参数：HeatTempDown |
| 245 | UserFanMode | RW | -1000..32767 | 0 | 代码宏定义参数：UserFanMode |
| 246 | UserFanPressure | RW | -1000..32767 | 50 | 代码宏定义参数：UserFanPressure |
| 247 | UserFanHand | RW | -1000..32767 | 500 | 代码宏定义参数：UserFanHand |
| 248 | HumUseSet | RW | -1000..32767 | 0 | 代码宏定义参数：HumUseSet |
| 249 | HeatTempGAP | RW | 0..100 | 20 | 代码宏定义参数：HeatTempGAP |
| 250 | Compuseful1_1 | RW | 0..255 | 1 | 压缩机相关参数/显示 |
| 251 | Compuseful1_2 | RW | 0..255 | 1 | 压缩机相关参数/显示 |
| 252 | Compuseful2_1 | RW | 0..255 | 1 | 压缩机相关参数/显示 |
| 253 | Compuseful2_2 | RW | 0..255 | 1 | 压缩机相关参数/显示 |
| 254 | Compuseful3_1 | RW | 0..255 | 1 | 压缩机相关参数/显示 |
| 255 | Compuseful3_2 | RW | 0..255 | 1 | 压缩机相关参数/显示 |
| 256 | Compuseful4_1 | RW | 0..255 | 1 | 压缩机相关参数/显示 |
| 257 | Compuseful4_2 | RW | 0..255 | 1 | 压缩机相关参数/显示 |
| 258 | - | RW | 0..255 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 259 | - | RW | 0..1 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 260 | VJumpUp | RW | 0..140 | 42 | 代码宏定义参数：VJumpUp |
| 261 | VJumpDn | RW | 0..140 | 39 | 代码宏定义参数：VJumpDn |
| 262 | EEVUp | RW | -200..999 | 10 | 代码宏定义参数：EEVUp |
| 263 | EEVDn | RW | 0..999 | 10 | 代码宏定义参数：EEVDn |
| 264 | VJumpEnable | RW | -1000..1 | 0 | 代码宏定义参数：VJumpEnable |
| 265 | VJumpUp2 | RW | -1000..140 | 48 | 代码宏定义参数：VJumpUp2 |
| 266 | VJumpDn2 | RW | -1000..140 | 45 | 代码宏定义参数：VJumpDn2 |
| 267 | EEVUp2 | RW | -1000..999 | 3 | 代码宏定义参数：EEVUp2 |
| 268 | EEVDn2 | RW | -1000..999 | 3 | 代码宏定义参数：EEVDn2 |
| 269 | - | RW | -1000..550 | 300 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 270 | HumUpGap1Set | RW | 0..500 | 100 | 代码宏定义参数：HumUpGap1Set |
| 271 | HumUpGap2Set | RW | 0..500 | 45 | 代码宏定义参数：HumUpGap2Set |
| 272 | HumDownGap1Set | RW | 0..500 | 0 | 代码宏定义参数：HumDownGap1Set |
| 273 | HumDownGap2Set | RW | 0..500 | 10 | 代码宏定义参数：HumDownGap2Set |
| 274 | HeatPumpUpGapSet | RW | 0..99 | 3 | 代码宏定义参数：HeatPumpUpGapSet |
| 275 | DownEnableSet | RW | 0..1 | 1 | 代码宏定义参数：DownEnableSet |
| 276 | UpEnableSet | RW | 0..1 | 1 | 代码宏定义参数：UpEnableSet |
| 277 | EEVCloseMinSizeSet_C | RW | 0..999 | 200 | 代码宏定义参数：EEVCloseMinSizeSet_C |
| 278 | MachineTypeSet1CON | RW | -300..800 | 0 | 18  -30~55 |
| 279 | MachineTypeSet1COFF | RW | -300..800 | 600 | 43   -30~55 |
| 280 | MachineTypeSet1HON | RW | -300..800 | -120 | 16  -30~55 |
| 281 | MachineTypeSet1HOFF | RW | -300..800 | 350 | 28   -30~55 |
| 282 | AI2_Pa_V_MIN | RW | 0..100 | 5 | AI0/AI3 压差/风压电压量程下限，0.1V |
| 283 | AI2_Pa_V_MAX | RW | 0..100 | 100 | AI0/AI3 压差/风压电压量程上限，0.1V |
| 284 | AI2_Pa_D_MIN | RW | 0..9999 | 0 | AI0/AI3 压差/风压工程量下限，Pa |
| 285 | AI2_Pa_D_MAX | RW | 0..9999 | 3000 | AI0/AI3 压差/风压工程量上限，Pa |
| 286 | AI3_mh_V_MIN | RW | 0..100 | 5 | AI3 风量/风速电压量程下限，0.1V |
| 287 | AI3_mh_V_MAX | RW | 0..100 | 100 | AI3 风量/风速电压量程上限，0.1V |
| 288 | AI3_mh_D_MIN | RW | 0..30000 | 0 | AI3 风量/风速工程量下限 |
| 289 | AI3_mh_D_MAX | RW | 0..30000 | 30 | AI3 风量/风速工程量上限 |
| 290 | Fan_Ctrl_Cycle | RW | 0..999 | 10 | 风机相关参数/显示 |
| 291 | Fan_Ctrl_Step | RW | 0..100 | 10 | 风机相关参数/显示 |
| 292 | Fan_Ctrl_Min | RW | 0..1000 | 300 | 风机相关参数/显示 |
| 293 | Fan_Ctrl_Max | RW | 0..1000 | 900 | 风机相关参数/显示 |
| 294 | Fan_Ctrl_PA | RW | 0..9999 | 20 | 风机相关参数/显示 |
| 295 | Fan_Ctrl_Div | RW | 0..9999 | 3 | 风机相关参数/显示 |
| 296 | Fan_Ctrl_HandEnable | RW | 0..1 | 0 | 风机相关参数/显示 |
| 297 | Fan_Ctrl_HandPa | RW | 0..1000 | 900 | 风机相关参数/显示 |
| 298 | Y02HandEnable | RW | 0..1 | 0 | 代码宏定义参数：Y02HandEnable |
| 299 | DA0TempSet | RW | 400..650 | 500 | 代码宏定义参数：DA0TempSet |
| 300 | Con_EEVAdjustTimeSet | RW | 1..999 | 30 | 代码宏定义参数：Con_EEVAdjustTimeSet |
| 301 | Con_EEVAdjustStep | RW | 1..999 | 1 | 代码宏定义参数：Con_EEVAdjustStep |
| 302 | Con_EEVAdjustMAX | RW | 1..999 | 500 | 代码宏定义参数：Con_EEVAdjustMAX |
| 303 | Con_EEVAdjustMIN | RW | 1..999 | 50 | 代码宏定义参数：Con_EEVAdjustMIN |
| 304 | CondReheat | RW | 0..1 | 0 | 代码宏定义参数：CondReheat |
| 305 | Eleheatfunction | RW | 0..3 | 2 | 代码宏定义参数：Eleheatfunction |
| 306 | SummerElectricheat | RW | 0..1 | 1 | 代码宏定义参数：SummerElectricheat |
| 307 | SupplyFanType | RW | 0..3 | 3 | 代码宏定义参数：SupplyFanType |
| 308 | WindSet | RW | 0..2 | 0 | 代码宏定义参数：WindSet |
| 309 | OutFanType | RW | 0..1 | 0 | 代码宏定义参数：OutFanType |
| 310 | Fan_Ctrl_PA1 | RW | 0..9999 | 3000 | 风机相关参数/显示 |
| 311 | Fan_Ctrl_Div1 | RW | 0..9999 | 10 | 风机相关参数/显示 |
| 312 | FanSpeedSet | RW | 0..1 | 1 | 风机相关参数/显示 |
| 313 | FanPaSet | RW | 0..1 | 1 | 风机相关参数/显示 |
| 314 | DA0Select | RW | 0..1 | 0 | 代码宏定义参数：DA0Select |
| 315 | CompControlModeSet | RW | 0..1 | 0 | 规格书扩展参数：来电自启/开关机时序相关使能 |
| 316 | EnvCoolFullLoadTempSet | RW | 150..300 | 210 | 规格书扩展参数：制冷/通风温度或时序参数 |
| 317 | EnvCoolUnloadTempSet | RW | 150..300 | 180 | 规格书扩展参数：制热/预热温度或时序参数 |
| 318 | EnvHeatFullLoadTempSet | RW | -300..300 | 50 | 规格书扩展参数：环境温度控制HLM/HLC阈值 |
| 319 | EnvHeatUnloadTempSet | RW | -300..300 | 150 | 规格书扩展参数：环境温度控制HRM/HRC阈值 |
| 320 | AutoCoolHeatEnableSet | RW | 0..1 | 0 | 规格书扩展参数：自动冷热切换使能/模式 |
| 321 | QHBSet | RW | 10..80 | 50 | 规格书扩展参数：自动冷热切换温差/回差 |
| 322 | QHSSet | RW | 60..1200 | 600 | 规格书扩展参数：模式切换延时 |
| 323 | DisinfectRunTimeSet | RW | 0..999 | 60 | 规格书扩展参数：开机时序延时1 |
| 324 | ExhaustRunTimeSet | RW | 0..999 | 60 | 规格书扩展参数：关机时序延时1 |
| 325 | AfterModeSelectSet | RW | 0..1 | 0 | 规格书扩展参数：消排毒模式相关使能 |
| 326 | LastNormalModeSet | RW | 0..5 | 0 | 规格书扩展参数：消毒/排毒/自动模式选择 |
| 327 | PowerFailRecoverModeSet | RW | 0..2 | 0 | 规格书扩展参数：风阀/风机模式选择 |
| 328 | ExhaustFanDelaySet | RW | -90..90 | 30 | 排风机与送风机间隔，单位 s；正值=排风先开，负值=送风先开，0=同时启动；停机时送风/排风顺序反转；通风、制冷、制热、排毒和消排毒共用 |
| 329 | SupplyFanModeSet | RW | 0..4 | 3 | 规格书扩展参数：A-1系统PID初始N/Z档位 |
| 330 | ReturnFanModeSet | RW | 0..4 | 3 | 规格书扩展参数：A-2系统PID初始N/Z档位 |
| 331 | ExhaustFanModeSet | RW | 0..4 | 3 | 规格书扩展参数：B-1系统PID初始N/Z档位 |
| 332 | ReheatModeSet | RW | 0..4 | 3 | 规格书扩展参数：B-2系统PID初始N/Z档位 |
| 333 | PreheatModeSet | RW | 0..4 | 3 | 规格书扩展参数：C-1系统PID初始N/Z档位 |
| 334 | HumidifyModeSet | RW | 0..4 | 3 | 规格书扩展参数：C-2系统PID初始N/Z档位 |
| 335 | FreshValveModeSet | RW | 0..4 | 3 | 规格书扩展参数：D-1系统PID初始N/Z档位 |
| 336 | SupplyValveModeSet | RW | 0..4 | 1 | 规格书扩展参数：D-2系统PID初始N/Z档位 |
| 337 | ReturnValveModeSet | RW | 0..4 | 1 | 规格书扩展参数：PID/能量调节参数 |
| 338 | ExhaustValveModeSet | RW | 0..4 | 1 | 规格书扩展参数：PID/能量调节参数 |
| 339 | VentilationFanVoltSet | RW | 0..100 | 80 | 规格书扩展参数：PID比例/输出限制 |
| 340 | CoolHeatFanVoltSet | RW | 0..100 | 100 | 规格书扩展参数：PID积分/输出限制 |
| 341 | SupplyFanMinVoltSet | RW | 0..100 | 30 | 规格书扩展参数：PID微分/输出限制 |
| 342 | SupplyFanMaxVoltSet | RW | 0..100 | 100 | 规格书扩展参数：PID输出限制 |
| 343 | AirVolumeSet | RW | 0..30000 | 3000 | 规格书扩展参数：风量/维护累计阈值 |
| 344 | DuctAreaSet | RW | 1..1000 | 100 | 规格书扩展参数：维护提醒提前量/周期 |
| 345 | AirPressureSet | RW | 0..9999 | 300 | 规格书扩展参数：维护提醒累计时间 |
| 346 | MinValveOpenSet | RW | 0..1000 | 200 | 规格书扩展参数：维护提醒偏差 |
| 347 | ReheatKpSet | RW | 0..9999 | 50 | 规格书扩展参数：EEV蒸发温度保护阈值 |
| 348 | ReheatTiSet | RW | 1..9999 | 100 | 规格书扩展参数：EEV蒸发温度保护回差 |
| 349 | ReheatTdSet | RW | 0..9999 | 0 | 规格书扩展参数：EEV蒸发温度保护开度修正 |
| 350 | PreheatKpSet | RW | 0..9999 | 50 | 规格书扩展参数：EEV保护阈值2 |
| 351 | PreheatTiSet | RW | 1..9999 | 100 | 规格书扩展参数：EEV保护回差2 |
| 352 | PreheatTdSet | RW | 0..9999 | 0 | 规格书扩展参数：EEV保护开度修正2 |
| 353 | HumidKpSet | RW | 0..9999 | 50 | 规格书扩展参数：EEV保护阈值3 |
| 354 | HumidTiSet | RW | 1..9999 | 100 | 规格书扩展参数：EEV保护回差3 |
| 355 | HumidTdSet | RW | 0..9999 | 0 | 规格书扩展参数：EEV保护开度修正3 |
| 356 | PreheatStartTempSet | RW | -300..300 | 50 | 规格书扩展参数：防冻/新风温度保护阈值 |
| 357 | PreheatFullLoadTempSet | RW | -300..300 | 0 | 规格书扩展参数：防冻/新风温度恢复阈值 |
| 358 | ReheatFullOnDevSet | RW | 0..300 | 20 | 规格书扩展参数：送风高温保护阈值 |
| 359 | ReheatFullOffDevSet | RW | 0..300 | 5 | 规格书扩展参数：送风低温保护阈值 |
| 360 | HumidFullOnDevSet | RW | 0..100 | 50 | 规格书扩展参数：风机通风模式电压/比例 |
| 361 | HumidFullOffDevSet | RW | 0..100 | 20 | 规格书扩展参数：风机制冷制热模式电压/比例 |
| 362 | MaintenanceEnableSet | RW | 0..1 | 1 | 规格书扩展参数：风机模式电压使能 |
| 363 | MaintenanceIntervalSet | RW | 0..30000 | 0 | 规格书扩展参数：累计运行/维护计数 |
| 364 | MaintenanceResetSet | RW | 0..1 | 0 | 规格书扩展参数：再热/辅热使能 |
| 365 | EEVSpecPidEnableSet | RW | 0..1 | 0 | 规格书扩展参数：加湿使能 |
| 366 | EEVSuperHeatTargetSet | RW | 20..100 | 50 | 规格书扩展参数：加湿开启阈值 |
| 367 | EEVSuperHeatDeadSet | RW | 20..50 | 20 | 规格书扩展参数：加湿关闭阈值 |
| 368 | EEVPidKpSet | RW | 0..9999 | 5 | 规格书扩展参数：加湿延时/周期 |
| 369 | EEVPidTiSet | RW | 1..9999 | 100 | 规格书扩展参数：加湿输出比例/上限 |
| 370 | EEVPidTdSet | RW | 0..9999 | 0 | 规格书扩展参数：加湿输出下限/保留 |
| 371 | EEVStepLimitSet | RW | 1..100 | 20 | 规格书扩展参数：再热/辅热输出比例 |
| 372 | DefrostEEVStepSet | RW | 0..999 | 350 | 规格书扩展参数：EEV手动/维护开度 |
| 373 | MaintenanceBaseHourSet | RW | -32768..32767 | 0 | 规格书扩展参数：备用/诊断 |
| 374 | PreheatCtrlModeSet | RW | 0..1 | 0 | 预热控制模式 |
| 375 | PreheatAfterTempSet | RW | -300..300 | 50 | 预热后温度设定，0.1C |
| 376 | PreheatAfterDiffSet | RW | 1..100 | 40 | 预热后温差，0.1C |
| 377 | FreshValveCtrlBasisSet | RW | 0..2 | 0 | 新风阀控制依据：压差/CO2/手动等 |
| 378 | RoomPressureSet | RW | -500..500 | 0 | 房间压差设定，Pa |
| 379 | CO2Set | RW | 0..5000 | 800 | CO2 设定，ppm |
| 380 | FreshValveManualVoltSet | RW | 0..100 | 80 | 新风阀手动电压设定，0.1V |
| 381 | MixAirValveTypeSet | RW | 0..1 | 0 | 混风阀类型/使能 |
| 382 | HeatRecoveryEnableSet | RW | 0..1 | 0 | 热回收阀使能 |
| 383 | HeatRecoveryOnDevSet | RW | 0..300 | 20 | 热回收开启偏差 |
| 384 | HeatRecoveryOffDevSet | RW | 0..300 | 10 | 热回收关闭偏差 |
| 385 | PreheatSegSet | RW | 1..3 | 3 | 预热电加热段数：1=开关，2=1:2，3=1:2:4 |
| 386 | PressureProtectEnableSet | RW | 0..1 | 1 | 压差保护使能：0关闭，1启用，默认启用 |
| 387 | DebugBypassSensorSet | RW | 0..1 | 0 | AI0~AI4 显示调试旁路：0正常，1调试时不被SensorStatus盖成0/9999 |
| 388 | OutdoorUnitNumSet | RW | 1..4 | 1 | 外机板数量：1=A，2=A/B，3=A/B/C，4=A/B/C/D；用于屏蔽未配置系统的蒸发温度故障 |
| 389 | InPutStatusSet13 | RW | 0..1 | 0 | X05 输入极性：0=取反，1=不取反；用于过滤网压差/堵塞输入 |
| 390 | InPutStatusSet14 | RW | 0..1 | 0 | X06 输入极性：0=取反，1=不取反；用于加热/再热故障输入 |
| 391 | InPutStatusSet15 | RW | 0..1 | 0 | X07 输入极性：0=取反，1=不取反；用于新风预热故障输入 |
| 392 | InPutStatusSet16 | RW | 0..1 | 0 | X10 输入极性：0=取反，1=不取反；用于加湿器故障输入 |
| 393 | InPutStatusSet17 | RW | 0..1 | 0 | X11 输入极性：0=取反，1=不取反；用于排风机过载输入 |
| 394 | InPutStatusSet18 | RW | 0..1 | 0 | X12 输入极性：0=取反，1=不取反；用于回风机过载输入 |
| 395 | InPutStatusSet19 | RW | 0..1 | 0 | X13 输入极性：0=取反，1=不取反；用于漏水保护输入 |
| 396 | InPutStatusSet20 | RW | 0..1 | 0 | X14 输入极性：0=取反，1=不取反；用于回风压差开关输入 |
| 397 | InPutStatusSet21 | RW | 0..1 | 0 | X15 输入极性：0=取反，1=不取反；用于送风压差开关输入 |
| 398 | HMIOnOffCommandSet | RW | 0..1 | 0 | HMI/Modbus Poll 开停机命令：0=关机，1=开机；需 163=0 本地模式、700非故障、709=0 才能开机 |
| 399 | - | RW | -1000..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |

### 400~599

| 地址 | 变量/宏 | 权限 | 范围 | 默认 | 含义 |
|---:|---|---|---:|---:|---|
| 400 | VVFWarning | RW | -1000..32767 | 0 | 变频/频率相关显示或设定 |
| 401 | HumComType | RW | -1000..32767 | 0 | 代码宏定义参数：HumComType |
| 402 | HeatControlSet | RW | 0..1 | 0 | 代码宏定义参数：HeatControlSet |
| 403 | UpLoadGap1Set1 | RW | 0..255 | 30 | 代码宏定义参数：UpLoadGap1Set1 |
| 404 | UpLoadGap2Set1 | RW | 0..255 | 10 | 代码宏定义参数：UpLoadGap2Set1 |
| 405 | UpLoadTime1Set1 | RW | 0..255 | 5 | 代码宏定义参数：UpLoadTime1Set1 |
| 406 | UpLoadTime2Set1 | RW | 0..255 | 10 | 代码宏定义参数：UpLoadTime2Set1 |
| 407 | DownLoadGap1Set1 | RW | 0..255 | 10 | 代码宏定义参数：DownLoadGap1Set1 |
| 408 | DownLoadGap2Set1 | RW | 0..255 | 20 | 代码宏定义参数：DownLoadGap2Set1 |
| 409 | DownLoadTime1Set1 | RW | 0..255 | 10 | 代码宏定义参数：DownLoadTime1Set1 |
| 410 | DownLoadTime2Set1 | RW | 0..255 | 5 | 代码宏定义参数：DownLoadTime2Set1 |
| 411 | EEVStartStepSet | RW | 0..500 | 200 | 电子膨胀阀起始开度，单位：步 |
| 412 | PidAdjustTimeSet1 | RW | 5..999 | 5 | 代码宏定义参数：PidAdjustTimeSet1 |
| 413 | AmpliFactor1 | RW | 0..999 | 50 | 代码宏定义参数：AmpliFactor1 |
| 414 | ISeparateTempDevSet1 | RW | 0..300 | 50 | 代码宏定义参数：ISeparateTempDevSet1 |
| 415 | MaxOutputTempDevSet1 | RW | 0..300 | 50 | 代码宏定义参数：MaxOutputTempDevSet1 |
| 416 | ProportionCoeSet1 | RW | 0..9999 | 10 | 代码宏定义参数：ProportionCoeSet1 |
| 417 | IntegralCoeSet1 | RW | 0..9999 | 200 | 代码宏定义参数：IntegralCoeSet1 |
| 418 | DerivativeCoeSet1 | RW | 0..9999 | 5 | 代码宏定义参数：DerivativeCoeSet1 |
| 419 | MaxOutTime1 | RW | 1..99 | 15 | 代码宏定义参数：MaxOutTime1 |
| 420 | MaxOutDV1 | RW | 1..100 | 30 | 代码宏定义参数：MaxOutDV1 |
| 421 | KeepTime | RW | 0..999 | 30 | 代码宏定义参数：KeepTime |
| 422 | PidAdjustTimeSet2 | RW | 5..999 | 5 | 代码宏定义参数：PidAdjustTimeSet2 |
| 423 | AmpliFactor2 | RW | 0..999 | 50 | 代码宏定义参数：AmpliFactor2 |
| 424 | ISeparateTempDevSet2 | RW | 0..300 | 50 | 代码宏定义参数：ISeparateTempDevSet2 |
| 425 | MaxOutputTempDevSet2 | RW | 0..300 | 50 | 代码宏定义参数：MaxOutputTempDevSet2 |
| 426 | ProportionCoeSet2 | RW | 0..9999 | 3 | 代码宏定义参数：ProportionCoeSet2 |
| 427 | IntegralCoeSet2 | RW | 0..9999 | 20 | 代码宏定义参数：IntegralCoeSet2 |
| 428 | DerivativeCoeSet2 | RW | 0..9999 | 1 | 代码宏定义参数：DerivativeCoeSet2 |
| 429 | MaxOutTime2 | RW | 1..99 | 15 | 代码宏定义参数：MaxOutTime2 |
| 430 | MaxOutDV2 | RW | 1..100 | 10 | 代码宏定义参数：MaxOutDV2 |
| 431 | CompControlSelect | RW | 0..1 | 0 | 压缩机相关参数/显示 |
| 432 | TempHumiSelectSet | RW | 0..1 | 0 | 湿度传感器类型选择：0=0-10V，1=4-20mA；自动同步460和463 |
| 433 | IndTempVolRanHigh | RW | 0..50 | 45 | 代码宏定义参数：IndTempVolRanHigh |
| 434 | IndTempVolRanLow | RW | 0..50 | 5 | 代码宏定义参数：IndTempVolRanLow |
| 435 | IndTempTempVolRanHigh | RW | 300..1500 | 900 | 代码宏定义参数：IndTempTempVolRanHigh |
| 436 | IndTempTempVolRanLow | RW | -800..0 | -300 | 代码宏定义参数：IndTempTempVolRanLow |
| 437 | IndHumiVolRanHigh | RW | 0..50 | 45 | 湿度电压输入上限，0.1V |
| 438 | IndHumiVolRanLow | RW | 0..50 | 5 | 湿度电压输入下限，0.1V |
| 439 | IndHumiHumiVolRanHigh | RW | 0..1000 | 1000 | 电压型湿度输出上限，0.1%RH |
| 440 | IndHumiHumiVolRanLow | RW | 0..1000 | 0 | 电压型湿度输出下限，0.1%RH |
| 441 | IndTempCurRanHigh | RW | 40..500 | 200 | 代码宏定义参数：IndTempCurRanHigh |
| 442 | IndTempCurRanLow | RW | 0..200 | 40 | 代码宏定义参数：IndTempCurRanLow |
| 443 | IndTempTempCurRanHigh | RW | 300..1500 | 900 | 代码宏定义参数：IndTempTempCurRanHigh |
| 444 | IndTempTempCurRanLow | RW | -800..0 | -300 | 代码宏定义参数：IndTempTempCurRanLow |
| 445 | IndHumiCurRanHigh | RW | 40..500 | 200 | 湿度电流输入上限，0.1mA |
| 446 | IndHumiCurRanLow | RW | 0..200 | 40 | 湿度电流输入下限，0.1mA |
| 447 | IndHumiHumiCurRanHigh | RW | 0..1000 | 1000 | 电流型湿度输出上限，0.1%RH |
| 448 | IndHumiHumiCurRanLow | RW | 0..1000 | 0 | 电流型湿度输出下限，0.1%RH |
| 449 | - | RW | 0..59 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 450 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 451 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 452 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 453 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 454 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 455 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 456 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 457 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 458 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 459 | A0TypeSet | RW | 0..1 | 0 | AI0 房间压差输入类型：0=0-10V，1=4-20mA |
| 460 | A1TypeSet | RW | 0..1 | 0 | AI1 房间湿度输入类型：0=0-10V，1=4-20mA，通常由432同步 |
| 461 | A2TypeSet | RW | 0..1 | 0 | AI2 CO2输入类型：0=0-10V，1=4-20mA |
| 462 | A3TypeSet | RW | 0..1 | 0 | AI3 送风压力/风速输入类型：0=0-10V，1=4-20mA |
| 463 | A4TypeSet | RW | 0..1 | 0 | AI4 新风湿度输入类型：0=0-10V，1=4-20mA，通常由432同步 |
| 464 | A5TypeSet | RO(隐藏) | -9999..32767 | 0 | A5TypeSet历史保留，A5实际是NTC0，不按普通AI切换 |
| 465 | A465ValueSet | RO(隐藏) | 1000..1400 | 1200 | A465ValueSet，量程/工厂值，默认1200，隐藏只读 |
| 466 | A466ValueSet | RO(隐藏) | 4500..5500 | 5000 | A466ValueSet，CO2满量程ppm，默认5000，隐藏只读 |
| 467 | A467ValueSet | RO(隐藏) | 3000..3600 | 3300 | A467ValueSet，量程/工厂值，默认3300，隐藏只读 |
| 468 | - | RO(隐藏) | 0..2 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 469 | - | RO(隐藏) | 0..2 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 470 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 471 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 472 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 473 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 474 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 475 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 476 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 477 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 478 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 479 | - | RO(隐藏) | -9999..32767 | 0 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 480 | - | RO(隐藏) | 29000..32767 | 30000 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 481 | - | RO(隐藏) | 29000..32767 | 30000 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 482 | - | RO(隐藏) | 29000..32767 | 30000 | 保存参数但未找到明确宏名；按min/max可写，普通HMI不建议作为常用点 |
| 483 | UserA16ValueSet | RO(隐藏) | 29000..32767 | 30000 | AI/NTC校准偏移值 |
| 484 | UserA15ValueSet | RO(隐藏) | -9999..32767 | 0 | AI/NTC校准偏移值 |
| 485 | UserA14ValueSet | RO(隐藏) | -9999..32767 | 0 | AI/NTC校准偏移值 |
| 486 | UserA13ValueSet | RO(隐藏) | -9999..32767 | 0 | AI/NTC校准偏移值 |
| 487 | UserA12ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 488 | UserA11ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 489 | UserA10ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 490 | UserA9ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 491 | UserA8ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 492 | UserA7ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 493 | UserA6ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 494 | UserA5ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 495 | UserA4ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 496 | UserA3ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 497 | UserA2ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 498 | UserA1ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 499 | UserA0ValueSet | RO(隐藏) | -500..500 | 0 | AI/NTC校准偏移值 |
| 500 | PressSensorAI0Disp | RO |  |  | AI0 房间压差旧显示地址，Pa；SensorStatus异常时可能显示9999 |
| 501 | HumiditySensorAI1Disp | RO |  |  | AI1 房间湿度显示，0.1%RH，1000=100.0% |
| 502 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 503 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 504 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 505 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 506 | DA0ValueDisp | RO |  |  | 代码宏定义参数：DA0ValueDisp |
| 507 | DA1ValueDisp | RO |  |  | 代码宏定义参数：DA1ValueDisp |
| 508 | EnviDewpointTempSet | RO |  |  | 代码宏定义参数：EnviDewpointTempSet |
| 509 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 510 | SysOutTempAI10Disp | RO |  |  | NTC1 送风温度显示，0.1C；实际赋值 AI[6]=NTC1 |
| 511 | RoomTempAI11Disp | RO |  |  | NTC0 房间/回风温度显示，0.1C；实际赋值 AI[5]=NTC0 |
| 512 | Innercoil1Disp / FreshAirTempDisp | RO |  |  | NTC2 新风温度显示，0.1C；历史宏名叫 Innercoil1Disp，实际赋值 AI[7]=NTC2 |
| 513 | Innercoil2Disp / PreheatAfterTempDisp | RO |  |  | NTC3 预热后温度显示，0.1C；历史宏名叫 Innercoil2Disp，实际赋值 AI[8]=NTC3 |
| 514 | Innercoil3Disp / EvapTempB1Disp | RO |  |  | NTC6 B-1蒸发温度显示，0.1C；历史地址顺序不是 NTC 顺序 |
| 515 | CompEva14Disp | RO |  |  | NTC4 A-1蒸发温度显示，0.1C |
| 516 | CompEva15Disp | RO |  |  | NTC5 A-2蒸发温度显示，0.1C |
| 517 | Innercoil6Disp / EvapTempB2Disp | RO |  |  | NTC7 B-2蒸发温度显示，0.1C；历史地址顺序不是 NTC 顺序 |
| 518 | CompOD | RO |  |  | 压缩机相关显示/保留 |
| 519 | SysOutTempHumidDisp / FreshAirHumidityDisp | RO |  |  | AI4 新风湿度显示，0.1%RH |
| 520 | EvapTempC1Disp | RO |  |  | NTC8 C-1蒸发温度显示，0.1C |
| 521 | EvapTempC2Disp / TouchScreenONOFF | RO |  |  | NTC9 C-2蒸发温度显示，0.1C；该地址有历史宏复用，HMI按蒸发温度用途读即可 |
| 522 | EvapTempD1Disp / TryUseOver | RO |  |  | NTC10 D-1蒸发温度显示，0.1C；该地址有历史宏复用，HMI按蒸发温度用途读即可 |
| 523 | EvapTempD2Disp / TimeStatus | RO |  |  | NTC11 D-2蒸发温度显示，0.1C；该地址有历史宏复用，HMI按蒸发温度用途读即可 |
| 524 | SysErrorReset | RW(受限) | 0..1 |  | 本机故障复位寄存器：HMI 写 1 触发复位；写保护已单独放行 0/1 |
| 525 | RecorverSet | RO |  |  | 代码宏定义参数：RecorverSet |
| 526 | FixRecorverSet | RO |  |  | 代码宏定义参数：FixRecorverSet |
| 527 | UserRecorverSet | RO |  |  | 代码宏定义参数：UserRecorverSet |
| 528 | CompRunTimeClear | RO |  |  | 压缩机相关参数/显示 |
| 529 | HandStopAntiFree | RO |  |  | 代码宏定义参数：HandStopAntiFree |
| 530 | TryPassSetInput1 | RO |  |  | 代码宏定义参数：TryPassSetInput1 |
| 531 | StopOilHeatIng | RO |  |  | 代码宏定义参数：StopOilHeatIng |
| 532 | AIValueSetClear | RO |  |  | 代码宏定义参数：AIValueSetClear |
| 533 | ModeNumDispOld | RO |  |  | 代码宏定义参数：ModeNumDispOld |
| 534 | ErrorPitcureUSED | RO |  |  | 代码宏定义参数：ErrorPitcureUSED |
| 535 | TryPassSetInput2 | RO |  |  | 代码宏定义参数：TryPassSetInput2 |
| 536 | PumpHandCtrl | RO |  |  | 代码宏定义参数：PumpHandCtrl |
| 537 | ValueEEVFlag | RO |  |  | 代码宏定义参数：ValueEEVFlag |
| 538 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 539 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 540 | ModeNumDisp | RO |  |  | 代码宏定义参数：ModeNumDisp |
| 541 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 542 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 543 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 544 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 545 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 546 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 547 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 548 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 549 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 550 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 551 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 552 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 553 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 554 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 555 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 556 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 557 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 558 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 559 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 560 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 561 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 562 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 563 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 564 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 565 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 566 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 567 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 568 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 569 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 570 | CompNumDisp | RO |  |  | 压缩机相关参数/显示 |
| 571 | CompStatusDisp | RO |  |  | 压缩机相关参数/显示 |
| 572 | HandDefInDisp | RO |  |  | 代码宏定义参数：HandDefInDisp |
| 573 | HandDefOutDisp | RO |  |  | 代码宏定义参数：HandDefOutDisp |
| 574 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 575 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 576 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 577 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 578 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 579 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 580 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 581 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 582 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 583 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 584 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 585 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 586 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 587 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 588 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 589 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 590 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 591 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 592 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 593 | InitPowerDisp | RO |  |  | 代码宏定义参数：InitPowerDisp |
| 594 | COMP1ComunicateErr | RO |  |  | 1#模块通讯故障 |
| 595 | COMP2ComunicateErr | RO |  |  | 2#模块通讯故障 |
| 596 | COMP3ComunicateErr | RO |  |  | 3#模块通讯故障 |
| 597 | COMP4ComunicateErr | RO |  |  | 4#模块通讯故障 |
| 598 | FanVVFErr | RO |  |  | 风机变频故障 |
| 599 | TSysInTempErr | RO |  |  | NTC3预热后温度故障 |

### 600~799

| 地址 | 变量/宏 | 权限 | 范围 | 默认 | 含义 |
|---:|---|---|---:|---:|---|
| 600 | TSysOutTempErr | RO |  |  | 复用故障位：NTC2新风温度故障，或加湿器故障/房间湿度故障导致加湿保护停机 |
| 601 | UserSidePumpOverLoadErr | RO |  |  | 用户侧水泵/负载过载 |
| 602 | AntiFreezeErr | RO |  |  | 防冻保护 |
| 603 | SysInTempErr | RO |  |  | NTC0房间/回风温度故障 |
| 604 | SysOutTempErr | RO |  |  | NTC1送风温度故障 |
| 605 | EnviTempErr | RO |  |  | 综合联锁/保护故障：火警、风阀联锁、漏水、排风/回风过载、加热故障、预热故障、X0电源/相序/急停等 |
| 606 | PLCComunicateErr | RO |  |  | PLC通讯故障 |
| 607 | DIPError | RO |  |  | DIP设置异常 |
| 608 | WriteEEpromErr | RO |  |  | EEPROM写入故障 |
| 609 | HumityTempErr | RO |  |  | 温湿度通讯/传感故障 |
| 610 | ValveCtrlBoardErr | RO |  |  | 阀控板通讯故障 |
| 611 | SystemComunicateErr | RO |  |  | 系统通讯故障 |
| 612 | Innercoil1TempErr | RO |  |  | NTC4 A-1蒸发温度故障 |
| 613 | Innercoil2TempErr | RO |  |  | NTC5 A-2蒸发温度故障 |
| 614 | Innercoil3TempErr | RO |  |  | NTC6 B-1蒸发温度故障 |
| 615 | Innercoil4TempErr | RO |  |  | NTC7 B-2蒸发温度故障 |
| 616 | AI2Err | RO |  |  | AI2 CO2故障 |
| 617 | AI3Err | RO |  |  | AI3风压/风速故障 |
| 618 | ROOMTempErr | RO |  |  | NTC0房间/回风温度故障 |
| 619 | ROOMHumidtyErr | RO |  |  | AI1房间湿度故障 |
| 620 | SysOutHumidErr | RO |  |  | AI4新风湿度故障 |
| 621 | SysOutTempLowErr | RO |  |  | 送风低温保护 |
| 622 | SysOutTempHightErr | RO |  |  | 送风高温保护 |
| 623 | EvapTempC1Err | RO |  |  | NTC8 C-1蒸发温度故障 |
| 624 | EvapTempC2Err | RO |  |  | NTC9 C-2蒸发温度故障 |
| 625 | EvapTempD1Err | RO |  |  | NTC10 D-1蒸发温度故障 |
| 626 | EvapTempD2Err | RO |  |  | NTC11 D-2蒸发温度故障 |
| 627 | AI0Err | RO |  |  | AI0房间压差故障 |
| 628 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 629 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 630 | SYSErr1 | RO |  |  | SYSErr1，故障位图1，bit0~15对应594~609，HMI按uint16/HEX显示 |
| 631 | SYSErr2 | RO |  |  | SYSErr2，故障位图2，bit0~14对应610~624，HMI按uint16/HEX显示，别按有符号数 |
| 632 | SYSErr3 | RO |  |  | SYSErr3，扩展故障位图：AI0、C/D蒸发温度、C/D蒸发低温保护 |
| 633 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 634 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 635 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 636 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 637 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 638 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 639 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 640 | Innercoil1Err | RO |  |  | A-1蒸发低温保护 |
| 641 | Innercoil2Err | RO |  |  | A-2蒸发低温保护 |
| 642 | Innercoil3Err | RO |  |  | B-1蒸发低温保护 |
| 643 | Innercoil4Err | RO |  |  | B-2蒸发低温保护 |
| 644 | EvapTempC1LowErr | RO |  |  | C-1蒸发低温保护 |
| 645 | EvapTempC2LowErr | RO |  |  | C-2蒸发低温保护 |
| 646 | EvapTempD1LowErr | RO |  |  | D-1蒸发低温保护 |
| 647 | EvapTempD2LowErr | RO |  |  | D-2蒸发低温保护 |
| 648 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 649 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 650 | PIDtemp0 | RO |  |  | 代码宏定义参数：PIDtemp0 |
| 651 | PIDtemp1 | RO |  |  | 代码宏定义参数：PIDtemp1 |
| 652 | PIDtemp2 | RO |  |  | 代码宏定义参数：PIDtemp2 |
| 653 | PID0PriVal | RO |  |  | 代码宏定义参数：PID0PriVal |
| 654 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 655 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 656 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 657 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 658 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 659 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 660 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 661 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 662 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 663 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 664 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 665 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 666 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 667 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 668 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 669 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 670 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 671 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 672 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 673 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 674 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 675 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 676 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 677 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 678 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 679 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 680 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 681 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 682 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 683 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 684 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 685 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 686 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 687 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 688 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 689 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 690 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 691 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 692 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 693 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 694 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 695 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 696 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 697 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 698 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 699 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 700 | SysStatus | RO |  |  | 系统状态：0正常停机，1禁止/远程停机，2故障停机，3定时停机，4正常运行，5定时运行；你读到 2 就是故障停机 |
| 701 | UseTimeFullWindow | RO |  |  | UseTimeFullWindow 使用时间/窗口状态 |
| 702 | LoadOutput | RO |  |  | LoadOutput 加载输出/能量状态 |
| 703 | ErrTotal | RO |  |  | ErrTotal 累计故障次数，不是当前故障个数 |
| 704 | MaxUseCompNumDisp | RO |  |  | 最大可用压缩机数显示；读到 2 表示当前可用 2 台压缩机；不是故障复位地址 |
| 705 | MaxCompDefRun | RO |  |  | 代码宏定义参数：MaxCompDefRun |
| 706 | PreFrzStatus | RO |  |  | 代码宏定义参数：PreFrzStatus |
| 707 | SystemNengry | RO |  |  | 代码宏定义参数：SystemNengry |
| 708 | NergryWorkCount | RO |  |  | 代码宏定义参数：NergryWorkCount |
| 709 | SysStep | RO |  |  | SysStep 系统步骤 |
| 710 | SysErrStatus | RO |  |  | SysErrStatus 当前故障状态 |
| 711 | UserSideControlTemp | RO |  |  | UserSideControlTemp 用户侧控制温度，0.1C |
| 712 | RealTemp | RO |  |  | 代码宏定义参数：RealTemp |
| 713 | UserPumpHCount | RO |  |  | 代码宏定义参数：UserPumpHCount |
| 714 | CtrlDisp | RO |  |  | 代码宏定义参数：CtrlDisp |
| 715 | CanCheckLow2Falg | RO |  |  | 代码宏定义参数：CanCheckLow2Falg |
| 716 | CheckHeatWaterPumpFlag | RO |  |  | 代码宏定义参数：CheckHeatWaterPumpFlag |
| 717 | ScreenChange | RO |  |  | ScreenChange 页面切换计数/状态 |
| 718 | UserPumpCount | RO |  |  | 代码宏定义参数：UserPumpCount |
| 719 | AntiFreColdOFFTime | RO |  |  | 代码宏定义参数：AntiFreColdOFFTime |
| 720 | SysErrNum | RO |  |  | 代码宏定义参数：SysErrNum |
| 721 | MErrNum | RO |  |  | 代码宏定义参数：MErrNum |
| 722 | AntiFreColdStep | RO |  |  | 代码宏定义参数：AntiFreColdStep |
| 723 | OilHeatingFlag | RO |  |  | 代码宏定义参数：OilHeatingFlag |
| 724 | FreezeOnSysFlag | RO |  |  | 代码宏定义参数：FreezeOnSysFlag |
| 725 | SysDefOnHeaterFlag | RO |  |  | 代码宏定义参数：SysDefOnHeaterFlag |
| 726 | CheckUserSidePumpFlag | RO |  |  | 代码宏定义参数：CheckUserSidePumpFlag |
| 727 | MaxUseCompNum | RO |  |  | 代码宏定义参数：MaxUseCompNum |
| 728 | ValueAIFlag | RO |  |  | 代码宏定义参数：ValueAIFlag |
| 729 | DispCheck | RO |  |  | 代码宏定义参数：DispCheck |
| 730 | WidControlCount | RO |  |  | 代码宏定义参数：WidControlCount |
| 731 | TempUp | RO |  |  | 代码宏定义参数：TempUp |
| 732 | TempDown | RO |  |  | 代码宏定义参数：TempDown |
| 733 | ControlLock | RO |  |  | 代码宏定义参数：ControlLock |
| 734 | ErrSecretInput | RO |  |  | 代码宏定义参数：ErrSecretInput |
| 735 | TMOnOffFlag | RO |  |  | 代码宏定义参数：TMOnOffFlag |
| 736 | SysUrgencyStop | RO |  |  | 代码宏定义参数：SysUrgencyStop |
| 737 | EnviOFFfalg | RO |  |  | 代码宏定义参数：EnviOFFfalg |
| 738 | RealTempDisp | RO |  |  | 代码宏定义参数：RealTempDisp |
| 739 | ControlTempDisp | RO |  |  | 代码宏定义参数：ControlTempDisp |
| 740 | ModeAI0Check | RO |  |  | 代码宏定义参数：ModeAI0Check |
| 741 | ModeAI1Check | RO |  |  | 代码宏定义参数：ModeAI1Check |
| 742 | ModeAI2Check | RO |  |  | 代码宏定义参数：ModeAI2Check |
| 743 | ModeAI3Check | RO |  |  | 代码宏定义参数：ModeAI3Check |
| 744 | ModeAI4Check | RO |  |  | 代码宏定义参数：ModeAI4Check |
| 745 | ModeAI5Check | RO |  |  | 代码宏定义参数：ModeAI5Check |
| 746 | ModeAI6Check | RO |  |  | 代码宏定义参数：ModeAI6Check |
| 747 | ModeAI7Check | RO |  |  | 代码宏定义参数：ModeAI7Check |
| 748 | ModeAI8Check | RO |  |  | 代码宏定义参数：ModeAI8Check |
| 749 | ModeAI9Check | RO |  |  | 代码宏定义参数：ModeAI9Check |
| 750 | ModeAI10Check | RO |  |  | 代码宏定义参数：ModeAI10Check |
| 751 | ModeAI11Check | RO |  |  | 代码宏定义参数：ModeAI11Check |
| 752 | ModeAI12Check | RO |  |  | 代码宏定义参数：ModeAI12Check |
| 753 | ModeAI13Check | RO |  |  | 代码宏定义参数：ModeAI13Check |
| 754 | ModeAI14Check | RO |  |  | 代码宏定义参数：ModeAI14Check |
| 755 | ModeAI15Check | RO |  |  | 代码宏定义参数：ModeAI15Check |
| 756 | ModeAI16Check | RO |  |  | 代码宏定义参数：ModeAI16Check |
| 757 | ModeAI17Check | RO |  |  | 代码宏定义参数：ModeAI17Check |
| 758 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 759 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 760 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 761 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 762 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 763 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 764 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 765 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 766 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 767 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 768 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 769 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 770 | MainOverHeat1Disp | RO |  |  | 代码宏定义参数：MainOverHeat1Disp |
| 771 | MainOverHeat2Disp | RO |  |  | 代码宏定义参数：MainOverHeat2Disp |
| 772 | MainOverHeat3Disp | RO |  |  | 代码宏定义参数：MainOverHeat3Disp |
| 773 | MainOverHeat4Disp | RO |  |  | 代码宏定义参数：MainOverHeat4Disp |
| 774 | MainOverHeat5Disp | RO |  |  | 代码宏定义参数：MainOverHeat5Disp |
| 775 | MainOverHeat6Disp | RO |  |  | 代码宏定义参数：MainOverHeat6Disp |
| 776 | MainOverHeat7Disp | RO |  |  | 代码宏定义参数：MainOverHeat7Disp |
| 777 | MainOverHeat8Disp | RO |  |  | 代码宏定义参数：MainOverHeat8Disp |
| 778 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 779 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 780 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 781 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 782 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 783 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 784 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 785 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 786 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 787 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 788 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 789 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 790 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 791 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 792 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 793 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 794 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 795 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 796 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 797 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 798 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 799 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |

### 800~999

| 地址 | 变量/宏 | 权限 | 范围 | 默认 | 含义 |
|---:|---|---|---:|---:|---|
| 800 | Comp1Temp_OK_Flag | RO |  |  | 压缩机相关参数/显示 |
| 801 | Comp2Temp_OK_Flag | RO |  |  | 压缩机相关参数/显示 |
| 802 | Comp3Temp_OK_Flag | RO |  |  | 压缩机相关参数/显示 |
| 803 | Comp4Temp_OK_Flag | RO |  |  | 压缩机相关参数/显示 |
| 804 | Comp5Temp_OK_Flag | RO |  |  | 压缩机相关参数/显示 |
| 805 | Comp6Temp_OK_Flag | RO |  |  | 压缩机相关参数/显示 |
| 806 | Comp7Temp_OK_Flag | RO |  |  | 压缩机相关参数/显示 |
| 807 | Comp8Temp_OK_Flag | RO |  |  | 压缩机相关参数/显示 |
| 808 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 809 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 810 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 811 | ONEnviTemp1Set | RO |  |  | -15  -20~20 |
| 812 | offEnviTemp2Set | RO |  |  | 43    20~60 |
| 813 | UserPumpErr | RO |  |  | 代码宏定义参数：UserPumpErr |
| 814 | UserPumpY00Dis | RO |  |  | 代码宏定义参数：UserPumpY00Dis |
| 815 | FanValveY01Dis | RO |  |  | 风机相关参数/显示 |
| 816 | HeaterY02Dis | RO |  |  | 代码宏定义参数：HeaterY02Dis |
| 817 | HeaterY03Dis | RO |  |  | 代码宏定义参数：HeaterY03Dis |
| 818 | HeaterY04Dis | RO |  |  | 代码宏定义参数：HeaterY04Dis |
| 819 | HeaterY05Dis | RO |  |  | 代码宏定义参数：HeaterY05Dis |
| 820 | HeaterY06Dis | RO |  |  | 代码宏定义参数：HeaterY06Dis |
| 821 | HeaterY07Dis | RO |  |  | 代码宏定义参数：HeaterY07Dis |
| 822 | OperatCurveDis | RO |  |  | 代码宏定义参数：OperatCurveDis |
| 823 | OperatCurveDis1 | RO |  |  | 代码宏定义参数：OperatCurveDis1 |
| 824 | PumpOverX00Dis | RO |  |  | 代码宏定义参数：PumpOverX00Dis |
| 825 | HeaterOverX03Dis | RO |  |  | 代码宏定义参数：HeaterOverX03Dis |
| 826 | FilterBlockingDis | RO |  |  | 代码宏定义参数：FilterBlockingDis |
| 827 | HumidifierX03Dis | RO |  |  | 湿度/加湿相关参数 |
| 828 | ErrorOutY00Dis | RO |  |  | 代码宏定义参数：ErrorOutY00Dis |
| 829 | FarSwitchX02Dis | RO |  |  | 代码宏定义参数：FarSwitchX02Dis |
| 830 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 831 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 832 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 833 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 834 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 835 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 836 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 837 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 838 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 839 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 840 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 841 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 842 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 843 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 844 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 845 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 846 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 847 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 848 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 849 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 850 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 851 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 852 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 853 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 854 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 855 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 856 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 857 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 858 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 859 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 860 | EEVPulseTimeSet | RO |  |  | 代码宏定义参数：EEVPulseTimeSet |
| 861 | ErrorOutFlag | RO |  |  | 代码宏定义参数：ErrorOutFlag |
| 862 | LoadFullFlag | RO |  |  | 代码宏定义参数：LoadFullFlag |
| 863 | LoadFullCount | RO |  |  | 代码宏定义参数：LoadFullCount |
| 864 | HaveDefOnHeater | RO |  |  | 代码宏定义参数：HaveDefOnHeater |
| 865 | NewStatus | RO |  |  | 代码宏定义参数：NewStatus |
| 866 | TEMP2 | RO |  |  | 代码宏定义参数：TEMP2 |
| 867 | TEMP3 | RO |  |  | 代码宏定义参数：TEMP3 |
| 868 | TEMP1 | RO |  |  | 代码宏定义参数：TEMP1 |
| 869 | FanDisp | RO |  |  | 风机相关参数/显示 |
| 870 | AntiDisp1 | RO |  |  | 代码宏定义参数：AntiDisp1 |
| 871 | ELENergyNeed | RO |  |  | 代码宏定义参数：ELENergyNeed |
| 872 | IndoorCtrlModeDisp | RO |  |  | 代码宏定义参数：IndoorCtrlModeDisp |
| 873 | IndoorPidModeDisp | RO |  |  | 代码宏定义参数：IndoorPidModeDisp |
| 874 | IndoorPidEKDisp | RO |  |  | 代码宏定义参数：IndoorPidEKDisp |
| 875 | IndoorPidEK1Disp | RO |  |  | 代码宏定义参数：IndoorPidEK1Disp |
| 876 | IndoorPidEK2Disp | RO |  |  | 代码宏定义参数：IndoorPidEK2Disp |
| 877 | IndoorPidYSDisp | RO |  |  | 代码宏定义参数：IndoorPidYSDisp |
| 878 | IndoorPidBXDisp | RO |  |  | 代码宏定义参数：IndoorPidBXDisp |
| 879 | IndoorPidZDisp | RO |  |  | 代码宏定义参数：IndoorPidZDisp |
| 880 | IndoorPidNDisp / ModuleEleVAL | RO |  |  | 代码宏定义参数：IndoorPidNDisp / ModuleEleVAL |
| 881 | IndoorTargetCompDisp / EMODSET1 | RO |  |  | 代码宏定义参数：IndoorTargetCompDisp / EMODSET1 |
| 882 | EnvControlStateDisp / EMODSET2 | RO |  |  | 代码宏定义参数：EnvControlStateDisp / EMODSET2 |
| 883 | AutoSwitchDirDisp / EMODSET3 | RO |  |  | 代码宏定义参数：AutoSwitchDirDisp / EMODSET3 |
| 884 | AutoSwitchCountDisp / EMODSET4 | RO |  |  | 代码宏定义参数：AutoSwitchCountDisp / EMODSET4 |
| 885 | DisinfectStepDisp / EMODSET5 | RO |  |  | 代码宏定义参数：DisinfectStepDisp / EMODSET5 |
| 886 | DisinfectRunCountDisp / EMODSET6 | RO |  |  | 代码宏定义参数：DisinfectRunCountDisp / EMODSET6 |
| 887 | ExhaustRunCountDisp / EMODSET7 | RO |  |  | 代码宏定义参数：ExhaustRunCountDisp / EMODSET7 |
| 888 | SupplyPressureOkDisp / EMODSET8 | RO |  |  | 代码宏定义参数：SupplyPressureOkDisp / EMODSET8 |
| 889 | ReturnPressureOkDisp / EMODSET9 | RO |  |  | 代码宏定义参数：ReturnPressureOkDisp / EMODSET9 |
| 890 | ReheatDemandDisp / EMODSET10 | RO |  |  | 代码宏定义参数：ReheatDemandDisp / EMODSET10 |
| 891 | PreheatDemandDisp / EMODSET11 | RO |  |  | 代码宏定义参数：PreheatDemandDisp / EMODSET11 |
| 892 | HumidDemandDisp / EMODSET12 | RO |  |  | 湿度/加湿相关参数 |
| 893 | OutputForbidReasonDisp / EMODSET13 | RO |  |  | 代码宏定义参数：OutputForbidReasonDisp / EMODSET13 |
| 894 | MaintenanceRemindFlag / EMODSET14 | RO |  |  | 代码宏定义参数：MaintenanceRemindFlag / EMODSET14 |
| 895 | IndoorSpecFaultDisp / EMODSET15 | RO |  |  | 代码宏定义参数：IndoorSpecFaultDisp / EMODSET15 |
| 896 | IndoorSpecVersionDisp / EMODSET16 | RO |  |  | 代码宏定义参数：IndoorSpecVersionDisp / EMODSET16 |
| 897 | FreshValveDemandDisp / EMODSET17 | RO |  |  | 代码宏定义参数：FreshValveDemandDisp / EMODSET17 |
| 898 | MixValveDemandDisp / EMODSET18 | RO |  |  | 代码宏定义参数：MixValveDemandDisp / EMODSET18 |
| 899 | HeatRecoveryDemandDisp / EMODSET19 | RO |  |  | 代码宏定义参数：HeatRecoveryDemandDisp / EMODSET19 |
| 900 | FanTargetDisp / EMODSET20 | RO |  |  | 风机相关参数/显示 |
| 901 | PreheatCtrlModeDisp / EMODSET21 | RO |  |  | 代码宏定义参数：PreheatCtrlModeDisp / EMODSET21 |
| 902 | RoomPressureDisp / EMODSET22 | RO |  |  | RoomPressureDisp 房间压差规格书显示地址，Pa |
| 903 | CO2Disp / EMODSET23 | RO |  |  | CO2Disp CO2浓度显示，ppm |
| 904 | AI0RawDisp / EMODSET24 | RO |  |  | AI0RawDisp AI0原始采样，约0.01V，400≈4.00V |
| 905 | AI1RawDisp | RO |  |  | AI1RawDisp AI1原始采样，约0.01V，400≈4.00V |
| 906 | AI2RawDisp | RO |  |  | AI2RawDisp AI2原始采样，约0.01V，400≈4.00V |
| 907 | AI3RawDisp | RO |  |  | AI3RawDisp AI3原始采样，约0.01V，400≈4.00V |
| 908 | AI4RawDisp | RO |  |  | AI4RawDisp AI4原始采样，约0.01V，400≈4.00V |
| 909 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 910 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 911 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 912 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 913 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 914 | PIDTEST1 | RO |  |  | 代码宏定义参数：PIDTEST1 |
| 915 | PIDTEST2 | RO |  |  | 代码宏定义参数：PIDTEST2 |
| 916 | PIDTEST3 | RO |  |  | 代码宏定义参数：PIDTEST3 |
| 917 | PIDTEST4 | RO |  |  | 代码宏定义参数：PIDTEST4 |
| 918 | PIDTEST5 | RO |  |  | 代码宏定义参数：PIDTEST5 |
| 919 | PIDTEST6 | RO |  |  | 代码宏定义参数：PIDTEST6 |
| 920 | PIDTEST7 | RO |  |  | 代码宏定义参数：PIDTEST7 |
| 921 | PIDTEST8 | RO |  |  | 代码宏定义参数：PIDTEST8 |
| 922 | PIDTEST9 | RO |  |  | 代码宏定义参数：PIDTEST9 |
| 923 | PIDTEST10 | RO |  |  | 代码宏定义参数：PIDTEST10 |
| 924 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 925 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 926 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 927 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 928 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 929 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 930 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 931 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 932 | SendSecond | RO |  |  | 代码宏定义参数：SendSecond |
| 933 | SendMinute | RO |  |  | 代码宏定义参数：SendMinute |
| 934 | SendHour | RO |  |  | 代码宏定义参数：SendHour |
| 935 | SendDay | RO |  |  | 代码宏定义参数：SendDay |
| 936 | SendMonth | RO |  |  | 代码宏定义参数：SendMonth |
| 937 | SendWeek | RO |  |  | 代码宏定义参数：SendWeek |
| 938 | SendYear | RO |  |  | 代码宏定义参数：SendYear |
| 939 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 940 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 941 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 942 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 943 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 944 | Old_VVFNumber1 | RO |  |  | 代码宏定义参数：Old_VVFNumber1 |
| 945 | Heatlevel | RO |  |  | 代码宏定义参数：Heatlevel |
| 946 | ModVVFOrder | RO |  |  | 外机/变频器状态读回 |
| 947 | ALLVVFOrder | RO |  |  | 代码宏定义参数：ALLVVFOrder |
| 948 | ModSelfStudy | RO |  |  | 代码宏定义参数：ModSelfStudy |
| 949 | ALLSelfStudy | RO |  |  | 代码宏定义参数：ALLSelfStudy |
| 950 | ModeCompControl1 | RO |  |  | 代码宏定义参数：ModeCompControl1 |
| 951 | ModeCompControl2 | RO |  |  | 代码宏定义参数：ModeCompControl2 |
| 952 | ModeCompVVFfre1 | RO |  |  | 代码宏定义参数：ModeCompVVFfre1 |
| 953 | ModeCompVVFfre2 | RO |  |  | 代码宏定义参数：ModeCompVVFfre2 |
| 954 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 955 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 956 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 957 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 958 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 959 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 960 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 961 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 962 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 963 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 964 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 965 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 966 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 967 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 968 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 969 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 970 | Version1 | RO |  |  | 代码宏定义参数：Version1 |
| 971 | Version2 | RO |  |  | 代码宏定义参数：Version2 |
| 972 | Version3 | RO |  |  | 代码宏定义参数：Version3 |
| 973 | Version4 | RO |  |  | 代码宏定义参数：Version4 |
| 974 | Version5 | RO |  |  | 代码宏定义参数：Version5 |
| 975 | Version6 | RO |  |  | 代码宏定义参数：Version6 |
| 976 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 977 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 978 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 979 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 980 | VVFDifNum | RO |  |  | 变频/频率相关显示或设定 |
| 981 | CloseWindow | RO |  |  | 代码宏定义参数：CloseWindow |
| 982 | HeaterFlag | RO |  |  | 代码宏定义参数：HeaterFlag |
| 983 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 984 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 985 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 986 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 987 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 988 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 989 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 990 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 991 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 992 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 993 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 994 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 995 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 996 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 997 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 998 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 999 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |

### 1000~1199

| 地址 | 变量/宏 | 权限 | 范围 | 默认 | 含义 |
|---:|---|---|---:|---:|---|
| 1000 | - | RO |  |  | 程序年份/版本年 |
| 1001 | - | RO |  |  | 程序月份/版本月 |
| 1002 | - | RO |  |  | 程序日期/版本日 |
| 1003 | - | RO |  |  | 程序版本高位 |
| 1004 | - | RO |  |  | 程序版本低位 |
| 1005 | - | RO |  |  | 程序版本/保留 |
| 1006 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1007 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1008 | DIPSet | RO |  |  | 代码宏定义参数：DIPSet |
| 1009 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1010 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1011 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1012 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1013 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1014 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1015 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1016 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1017 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1018 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1019 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1020 | VVFCompSetP0_02 | RO |  |  | 变频/频率相关显示或设定 |
| 1021 | VVFCompSetP0_07 | RO |  |  | 变频/频率相关显示或设定 |
| 1022 | VVFCompSetP0_12 | RO |  |  | 变频/频率相关显示或设定 |
| 1023 | VVFCompSetP2_01 | RO |  |  | 变频/频率相关显示或设定 |
| 1024 | VVFCompSetP2_02 | RO |  |  | 变频/频率相关显示或设定 |
| 1025 | VVFCompSetP5_08 | RO |  |  | 变频/频率相关显示或设定 |
| 1026 | VVFCompSetP5_14 | RO |  |  | 变频/频率相关显示或设定 |
| 1027 | VVFCompSetP6_00 | RO |  |  | 变频/频率相关显示或设定 |
| 1028 | VVFCompSetP6_01 | RO |  |  | 变频/频率相关显示或设定 |
| 1029 | VVFCompSetP6_02 | RO |  |  | 变频/频率相关显示或设定 |
| 1030 | VVFCompSetP6_03 | RO |  |  | 变频/频率相关显示或设定 |
| 1031 | VVFCompSetP6_04 | RO |  |  | 变频/频率相关显示或设定 |
| 1032 | VVFCompSetP6_05 | RO |  |  | 变频/频率相关显示或设定 |
| 1033 | VVFCompSetP6_06 | RO |  |  | 变频/频率相关显示或设定 |
| 1034 | VVFCompSetP6_08 | RO |  |  | 变频/频率相关显示或设定 |
| 1035 | VVFCompSetP6_10 | RO |  |  | 变频/频率相关显示或设定 |
| 1036 | VVFCompSetP6_11 | RO |  |  | 变频/频率相关显示或设定 |
| 1037 | VVFCompSetP9_00 | RO |  |  | 变频/频率相关显示或设定 |
| 1038 | VVFCompSetP9_01 | RO |  |  | 变频/频率相关显示或设定 |
| 1039 | VVFCompSetP9_04 | RO |  |  | 变频/频率相关显示或设定 |
| 1040 | VVFCompSetP9_06 | RO |  |  | 变频/频率相关显示或设定 |
| 1041 | VVFCompSetP9_07 | RO |  |  | 变频/频率相关显示或设定 |
| 1042 | VVFCompSetP9_10 | RO |  |  | 变频/频率相关显示或设定 |
| 1043 | VVFCompSetC0_02 | RO |  |  | 变频/频率相关显示或设定 |
| 1044 | VVFCompSetC0_03 | RO |  |  | 变频/频率相关显示或设定 |
| 1045 | VVFCompSetC0_04 | RO |  |  | 变频/频率相关显示或设定 |
| 1046 | VVFCompSetD0_11 | RO |  |  | 变频/频率相关显示或设定 |
| 1047 | VVFCompSetD0_12 | RO |  |  | 变频/频率相关显示或设定 |
| 1048 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1049 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1050 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1051 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1052 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1053 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1054 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1055 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1056 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1057 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1058 | VVFNumber1 | RO |  |  | 变频/频率相关显示或设定 |
| 1059 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1060 | VVFCompSet1 | RO |  |  | 变频/频率相关显示或设定 |
| 1061 | VVFCompSet2 | RO |  |  | 变频/频率相关显示或设定 |
| 1062 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1063 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1064 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1065 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1066 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1067 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1068 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1069 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1070 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1071 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1072 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1073 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1074 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1075 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1076 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1077 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1078 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1079 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1080 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1081 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1082 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1083 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1084 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1085 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1086 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1087 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1088 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1089 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1090 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1091 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1092 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1093 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1094 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1095 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1096 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1097 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1098 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1099 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1100 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1101 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1102 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1103 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1104 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1105 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1106 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1107 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1108 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1109 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1110 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1111 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1112 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1113 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1114 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1115 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1116 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1117 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1118 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1119 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1120 | MainFanSpeedDisp | RO |  |  | 主送风机转速显示 |
| 1121 | MainFanError | RO |  |  | 主送风机故障码 |
| 1122 | FanErrorReset | RO |  |  | 风机变频故障复位 |
| 1123 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1124 | MainFanSpeedCtrl | RO |  |  | 主送风机转速控制 |
| 1125 | MainFanPaDisp | RO |  |  | AI3送风压力显示，Pa |
| 1126 | MainFanm3hDisp | RO |  |  | AI3风量/风速显示 |
| 1127 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1128 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1129 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1130 | FanSpeedDisp | RO |  |  | 风机相关参数/显示 |
| 1131 | FanError | RO |  |  | 风机相关参数/显示 |
| 1132 | FanVoltage | RO |  |  | 风机相关参数/显示 |
| 1133 | VVFBaudRate | RO |  |  | 变频/频率相关显示或设定 |
| 1134 | FanSpeedCtrl | RO |  |  | 风机相关参数/显示 |
| 1135 | FanSpeedDisp2 | RO |  |  | 风机相关参数/显示 |
| 1136 | FanError2 | RO |  |  | 风机相关参数/显示 |
| 1137 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1138 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1139 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1140 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1141 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1142 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1143 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1144 | EEVCtrlNum | RO |  |  | 代码宏定义参数：EEVCtrlNum |
| 1145 | EEV1NewAddValue | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1146 | EEV2NewAddValue | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1147 | EEV3NewAddValue | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1148 | EEV4NewAddValue | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1149 | EEV5NewAddValue | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1150 | EEV6NewAddValue | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1151 | EEV7NewAddValue | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1152 | EEV8NewAddValue | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1153 | EEV1OldAddValue | RO |  |  | 电子膨胀阀当前/回读步数 |
| 1154 | EEV2OldAddValue | RO |  |  | 电子膨胀阀当前/回读步数 |
| 1155 | EEV3OldAddValue | RO |  |  | 电子膨胀阀当前/回读步数 |
| 1156 | EEV4OldAddValue | RO |  |  | 电子膨胀阀当前/回读步数 |
| 1157 | EEV5OldAddValue | RO |  |  | 电子膨胀阀当前/回读步数 |
| 1158 | EEV6OldAddValue | RO |  |  | 电子膨胀阀当前/回读步数 |
| 1159 | EEV7OldAddValue | RO |  |  | 电子膨胀阀当前/回读步数 |
| 1160 | EEV8OldAddValue | RO |  |  | 电子膨胀阀当前/回读步数 |
| 1161 | EEV1RunFlag | RO |  |  | 电子膨胀阀运行标志 |
| 1162 | EEV2RunFlag | RO |  |  | 电子膨胀阀运行标志 |
| 1163 | EEV3RunFlag | RO |  |  | 电子膨胀阀运行标志 |
| 1164 | EEV4RunFlag | RO |  |  | 电子膨胀阀运行标志 |
| 1165 | EEV5RunFlag | RO |  |  | 电子膨胀阀运行标志 |
| 1166 | EEV6RunFlag | RO |  |  | 电子膨胀阀运行标志 |
| 1167 | EEV7RunFlag | RO |  |  | 电子膨胀阀运行标志 |
| 1168 | EEV8RunFlag | RO |  |  | 电子膨胀阀运行标志 |
| 1169 | EEV_EnergryNeed1 | RO |  |  | 电子膨胀阀能量需求 |
| 1170 | EEV_EnergryNeed2 | RO |  |  | 电子膨胀阀能量需求 |
| 1171 | EEV_EnergryNeed3 | RO |  |  | 电子膨胀阀能量需求 |
| 1172 | EEV_EnergryNeed4 | RO |  |  | 电子膨胀阀能量需求 |
| 1173 | EEV_EnergryNeed5 | RO |  |  | 电子膨胀阀能量需求 |
| 1174 | EEV_EnergryNeed6 | RO |  |  | 电子膨胀阀能量需求 |
| 1175 | EEV_EnergryNeed7 | RO |  |  | 电子膨胀阀能量需求 |
| 1176 | EEV_EnergryNeed8 | RO |  |  | 电子膨胀阀能量需求 |
| 1177 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1178 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1179 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1180 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1181 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1182 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1183 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1184 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1185 | EEVInitialSizeSet0 | RO |  |  | 代码宏定义参数：EEVInitialSizeSet0 |
| 1186 | EEVInitialSizeSet | RO |  |  | 代码宏定义参数：EEVInitialSizeSet |
| 1187 | ENvironmentCount | RO |  |  | 代码宏定义参数：ENvironmentCount |
| 1188 | SuperheatSet | RO |  |  | 过热度相关参数 |
| 1189 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1190 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1191 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1192 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1193 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1194 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1195 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1196 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1197 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1198 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1199 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |

### 1200~1419

| 地址 | 变量/宏 | 权限 | 范围 | 默认 | 含义 |
|---:|---|---|---:|---:|---|
| 1200 | ConHeatValveEEV1 | RO |  |  | 热回收/冷凝热回收阀相关 |
| 1201 | ConHeatValveEEV2 | RO |  |  | 热回收/冷凝热回收阀相关 |
| 1202 | ConHeatValveEEV3 | RO |  |  | 热回收/冷凝热回收阀相关 |
| 1203 | ConHeatValveEEV4 | RO |  |  | 热回收/冷凝热回收阀相关 |
| 1204 | ConHeatValveEEV1_ON | RO |  |  | 热回收/冷凝热回收阀相关 |
| 1205 | ConHeatValveEEV2_ON | RO |  |  | 热回收/冷凝热回收阀相关 |
| 1206 | ConHeatValveEEV3_ON | RO |  |  | 热回收/冷凝热回收阀相关 |
| 1207 | ConHeatValveEEV4_ON | RO |  |  | 热回收/冷凝热回收阀相关 |
| 1208 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1209 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1210 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1211 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1212 | EEV1NewAddValue_ON | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1213 | EEV2NewAddValue_ON | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1214 | EEV3NewAddValue_ON | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1215 | EEV4NewAddValue_ON | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1216 | EEV5NewAddValue_ON | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1217 | EEV6NewAddValue_ON | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1218 | EEV7NewAddValue_ON | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1219 | EEV8NewAddValue_ON | RO |  |  | 电子膨胀阀目标步数/新开度 |
| 1220 | EEV1AddrValue_Disp | RO |  |  | 代码宏定义参数：EEV1AddrValue_Disp |
| 1221 | EEV2AddrValue_Disp | RO |  |  | 代码宏定义参数：EEV2AddrValue_Disp |
| 1222 | EEV3AddrValue_Disp | RO |  |  | 代码宏定义参数：EEV3AddrValue_Disp |
| 1223 | EEV4AddrValue_Disp | RO |  |  | 代码宏定义参数：EEV4AddrValue_Disp |
| 1224 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1225 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1226 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1227 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1228 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1229 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1230 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1231 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1232 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1233 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1234 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1235 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1236 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1237 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1238 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1239 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1240 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1241 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1242 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1243 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1244 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1245 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1246 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1247 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1248 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1249 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1250 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1251 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1252 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1253 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1254 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1255 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1256 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1257 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1258 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1259 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1260 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1261 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1262 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1263 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1264 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1265 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1266 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1267 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1268 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1269 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1270 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1271 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1272 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1273 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1274 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1275 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1276 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1277 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1278 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1279 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1280 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1281 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1282 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1283 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1284 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1285 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1286 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1287 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1288 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1289 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1290 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1291 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1292 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1293 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1294 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1295 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1296 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1297 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1298 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1299 | - | RO |  |  | 运行显示/状态镜像地址，未找到明确宏名；HMI只读，未用时可能为0或历史值 |
| 1300 | HandDebug | 条件RW |  |  | 手动调试总开关，条件写：SysStep=0 |
| 1301 | HandDebugY0 | 条件RW |  |  | 手动送风功能 |
| 1302 | HandDebugY00 | 条件RW |  |  | 1#压缩机手动 |
| 1303 | HandDebugY01 | 条件RW |  |  | 2#压缩机手动 |
| 1304 | HandDebugY02 | 条件RW |  |  | 1#相关输出手动 |
| 1305 | HandDebugY03 | 条件RW |  |  | 2#相关输出手动 |
| 1306 | HandDebugY04 | 条件RW |  |  | 1#四通阀手动 |
| 1307 | HandDebugY05 | 条件RW |  |  | 2#四通阀手动 |
| 1308 | HandDebugY06 | 条件RW |  |  | 1#其它输出手动 |
| 1309 | HandDebugY07 | 条件RW |  |  | 2#其它输出手动 |
| 1310 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1311 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1312 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1313 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1314 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1315 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1316 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1317 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1318 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1319 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1320 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1321 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1322 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1323 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1324 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1325 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1326 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1327 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1328 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1329 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1330 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1331 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1332 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1333 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1334 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1335 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1336 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1337 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1338 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1339 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1340 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1341 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1342 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1343 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1344 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1345 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1346 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1347 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1348 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1349 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1350 | X00InputDisp | RO | 0/1 |  | X00 电源/相序/急停保护输入状态，1=经极性和3秒滤波后有效 |
| 1351 | X01InputDisp | RO | 0/1 |  | X01 火警输入状态，1=报警/有效 |
| 1352 | X02InputDisp | RO | 0/1 |  | X02 远程开关/外部启停输入状态，1=有效 |
| 1353 | X03InputDisp | RO | 0/1 |  | X03 用户侧水泵/负载过载输入状态，1=报警/有效 |
| 1354 | X04InputDisp | RO | 0/1 |  | X04 风阀联锁输入状态，1=报警/有效 |
| 1355 | X05InputDisp | RO | 0/1 |  | X05 过滤网压差/堵塞输入状态，1=报警/有效 |
| 1356 | X06InputDisp | RO | 0/1 |  | X06 加热/再热故障输入状态，1=报警/有效 |
| 1357 | X07InputDisp | RO | 0/1 |  | X07 新风预热故障输入状态，1=报警/有效 |
| 1358 | X10InputDisp | RO | 0/1 |  | X10 加湿器故障输入状态，1=报警/有效 |
| 1359 | X11InputDisp | RO | 0/1 |  | X11 排风机过载输入状态，1=报警/有效 |
| 1360 | X12InputDisp | RO | 0/1 |  | X12 回风机过载输入状态，1=报警/有效 |
| 1361 | X13InputDisp | RO | 0/1 |  | X13 漏水保护输入状态，1=报警/有效 |
| 1362 | X14InputDisp | RO | 0/1 |  | X14 回风压差开关状态，代码按常闭接线取反后显示，1=压差满足/有效 |
| 1363 | X15InputDisp | RO | 0/1 |  | X15 送风压差开关状态，代码按常闭接线取反后显示，1=压差满足/有效 |
| 1364 | X16InputDisp | RO | 0 |  | V10 硬件无 X16 实体输入，固定显示 0 |
| 1365 | X17InputDisp | RO | 0 |  | V10 硬件无 X17 实体输入，固定显示 0 |
| 1366 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1367 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1368 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1369 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1370 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1371 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1372 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1373 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1374 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1375 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1376 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1377 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1378 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1379 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1380 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1381 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1382 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1383 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1384 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1385 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1386 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1387 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1388 | TimeStatus | RW | 0..1 | 0 | 定时运行目标：165=1进入定时模式后，0要求停机，1要求运行 |
| 1389 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1390 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1391 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1392 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1393 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1394 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1395 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1396 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1397 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1398 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1399 | - | 保留 |  |  | 工程/手动调试保留区，普通HMI不使用 |
| 1400 | ModComp1OnOFFFalg | RO/受限 |  |  | PLC控制：1#压缩机开关命令，只读/受限 |
| 1401 | ModComp1Frency | RO/受限 |  |  | PLC控制：1#压缩机频率给定，只读/受限 |
| 1402 | ModSysErrorReset | 条件RW |  |  | PLC控制：系统故障复位，允许写0/1 |
| 1403 | ModComp2OnOFFFalg | RO/受限 |  |  | PLC控制：2#压缩机开关命令，只读/受限 |
| 1404 | ModComp2Frency | RO/受限 |  |  | PLC控制：2#压缩机频率给定，只读/受限 |
| 1405 | ModRecorverSet | RO/受限 |  |  | PLC控制：恢复默认，只读/受限 |
| 1406 | ModUrgencyStop | 条件RW |  |  | PLC控制：急停信号，允许写0/1 |
| 1407 | Comp1Enable | RO/受限 |  |  | 1#压缩机使能 |
| 1408 | Comp2Enable | RO/受限 |  |  | 2#压缩机使能 |
| 1409 | - | RO/受限 |  |  |  |
| 1410 | ModComp1DefrostFlag | RO/受限 |  |  | 1#压缩机化霜信号 |
| 1411 | ModComp2DefrostFlag | RO/受限 |  |  | 2#压缩机化霜信号 |
| 1412 | - | 保留 |  |  | PLC控制保留地址，普通HMI不使用 |
| 1413 | - | 保留 |  |  | PLC控制保留地址，普通HMI不使用 |
| 1414 | - | 保留 |  |  | PLC控制保留地址，普通HMI不使用 |
| 1415 | - | 保留 |  |  | PLC控制保留地址，普通HMI不使用 |
| 1416 | - | 保留 |  |  | PLC控制保留地址，普通HMI不使用 |
| 1417 | - | 保留 |  |  | PLC控制保留地址，普通HMI不使用 |
| 1418 | - | 保留 |  |  | PLC控制保留地址，普通HMI不使用 |
| 1419 | - | 保留 |  |  | PLC控制保留地址，普通HMI不使用 |

### 1420~1549

| 地址 | 变量/宏 | 权限 | 范围 | 默认 | 含义 |
|---:|---|---|---:|---:|---|
| 1420 | ModDefrostAsk1 | RO |  |  | 代码宏定义参数：ModDefrostAsk1 |
| 1421 | ModDefrostAsk2 | RO |  |  | 代码宏定义参数：ModDefrostAsk2 |
| 1422 | ModEnviTempAI0Disp | RO |  |  | 代码宏定义参数：ModEnviTempAI0Disp |
| 1423 | ModSlaveTempAI20Disp | RO |  |  | 代码宏定义参数：ModSlaveTempAI20Disp |
| 1424 | ModSlaveTempAI21Disp | RO |  |  | 代码宏定义参数：ModSlaveTempAI21Disp |
| 1425 | ModComp1RunStatus | RO |  |  | 外机压缩机状态/运行时间读回 |
| 1426 | ModComp2RunStatus | RO |  |  | 外机压缩机状态/运行时间读回 |
| 1427 | ModComp1RunHourDisp | RO |  |  | 外机压缩机状态/运行时间读回 |
| 1428 | ModComp2RunHourDisp | RO |  |  | 外机压缩机状态/运行时间读回 |
| 1429 | ModErrTotal | RO |  |  | 代码宏定义参数：ModErrTotal |
| 1430 | ModMaxUseCompNumDisp | RO |  |  | 代码宏定义参数：ModMaxUseCompNumDisp |
| 1431 | ModFinTemp1AI5Disp | RO |  |  | 代码宏定义参数：ModFinTemp1AI5Disp |
| 1432 | ModFinTemp2AI7Disp | RO |  |  | 代码宏定义参数：ModFinTemp2AI7Disp |
| 1433 | ModCompExhaustAI12Disp | RO |  |  | 外机压缩机状态/运行时间读回 |
| 1434 | ModCompExhaustAI13Disp | RO |  |  | 外机压缩机状态/运行时间读回 |
| 1435 | ModMainTempAI16Disp | RO |  |  | 代码宏定义参数：ModMainTempAI16Disp |
| 1436 | ModMainTempAI17Disp | RO |  |  | 代码宏定义参数：ModMainTempAI17Disp |
| 1437 | ModMainOverHeat1Disp | RO |  |  | 代码宏定义参数：ModMainOverHeat1Disp |
| 1438 | ModMainOverHeat2Disp | RO |  |  | 代码宏定义参数：ModMainOverHeat2Disp |
| 1439 | ModEEV1OldAddValueDisp | RO |  |  | 代码宏定义参数：ModEEV1OldAddValueDisp |
| 1440 | ModEEV2OldAddValueDisp | RO |  |  | 代码宏定义参数：ModEEV2OldAddValueDisp |
| 1441 | Comp1VVFNumDisp | RO |  |  | 压缩机相关参数/显示 |
| 1442 | Comp2VVFNumDisp | RO |  |  | 压缩机相关参数/显示 |
| 1443 | ModHighPressDisp1 | RO |  |  | 外机高低压读回 |
| 1444 | ModLowPressDisp1 | RO |  |  | 外机高低压读回 |
| 1445 | ModHighPressDisp2 | RO |  |  | 外机高低压读回 |
| 1446 | ModLowPressDisp2 | RO |  |  | 外机高低压读回 |
| 1447 | ModVVFmodule_1 | RO |  |  | 外机/变频器状态读回 |
| 1448 | ModVVFmodule_2 | RO |  |  | 外机/变频器状态读回 |
| 1449 | ModVVF1OPVoltageDisp | RO |  |  | 外机/变频器状态读回 |
| 1450 | ModVVF1OPFreDisp | RO |  |  | 外机/变频器状态读回 |
| 1451 | ModVVF1OPCurrentDisp | RO |  |  | 外机/变频器状态读回 |
| 1452 | ModVVF1TorqueDisp | RO |  |  | 外机/变频器状态读回 |
| 1453 | ModVVF1OPTorqueDisp | RO |  |  | 外机/变频器状态读回 |
| 1454 | ModVVF1OPPowerDisp | RO |  |  | 外机/变频器状态读回 |
| 1455 | VVF1TempDisp | RO |  |  | 变频/频率相关显示或设定 |
| 1456 | ModVVF2OPVoltageDisp | RO |  |  | 外机/变频器状态读回 |
| 1457 | ModVVF2OPFreDisp | RO |  |  | 外机/变频器状态读回 |
| 1458 | ModVVF2OPCurrentDisp | RO |  |  | 外机/变频器状态读回 |
| 1459 | ModVVF2TorqueDisp | RO |  |  | 外机/变频器状态读回 |
| 1460 | ModVVF2OPTorqueDisp | RO |  |  | 外机/变频器状态读回 |
| 1461 | ModVVF2OPPowerDisp | RO |  |  | 外机/变频器状态读回 |
| 1462 | ModVVF2TempDisp | RO |  |  | 外机/变频器状态读回 |
| 1463 | ModFanSpeedCtrl | RO |  |  | 风机通讯状态读回 |
| 1464 | ModFanSpeedDisp | RO |  |  | 风机通讯状态读回 |
| 1465 | ModFanSpeedDisp2 | RO |  |  | 风机通讯状态读回 |
| 1466 | ModFanError | RO |  |  | 风机通讯状态读回 |
| 1467 | ModFanError2 | RO |  |  | 风机通讯状态读回 |
| 1468 | ModDA0ValueDisp | RO |  |  | 代码宏定义参数：ModDA0ValueDisp |
| 1469 | ModDA1ValueDisp | RO |  |  | 代码宏定义参数：ModDA1ValueDisp |
| 1470 | ModXYstatus | RO |  |  | 代码宏定义参数：ModXYstatus |
| 1471 | ModERR1Disp | RO |  |  | 模块故障字读回 |
| 1472 | ModERR2Disp | RO |  |  | 模块故障字读回 |
| 1473 | ModERR3Disp | RO |  |  | 模块故障字读回 |
| 1474 | ModERR4Disp | RO |  |  | 模块故障字读回 |
| 1475 | ModERR5Disp | RO |  |  | 模块故障字读回 |
| 1476 | ModERR6Disp | RO |  |  | 模块故障字读回 |
| 1477 | ModERR7Disp | RO |  |  | 模块故障字读回 |
| 1478 | ModERR8Disp | RO |  |  | 模块故障字读回 |
| 1479 | UserA0ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1480 | UserA1ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1481 | UserA2ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1482 | UserA3ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1483 | UserA4ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1484 | UserA5ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1485 | UserA6ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1486 | UserA7ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1487 | UserA8ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1488 | UserA9ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1489 | UserA10ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1490 | UserA11ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1491 | UserA12ValueSetTemp | RO |  |  | AI/NTC校准偏移值 |
| 1492 | EEVManuOpenSizeSet2 | RO |  |  | 代码宏定义参数：EEVManuOpenSizeSet2 |
| 1493 | ManuCtrlEEVSet2 | RO |  |  | 代码宏定义参数：ManuCtrlEEVSet2 |
| 1494 | EEV2ManuOpenSizeSet2 | RO |  |  | 代码宏定义参数：EEV2ManuOpenSizeSet2 |
| 1495 | ManuCtrlEEV2Set2 | RO |  |  | 代码宏定义参数：ManuCtrlEEV2Set2 |
| 1496 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1497 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1498 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1499 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1500 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1501 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1502 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1503 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1504 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1505 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1506 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1507 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1508 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1509 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1510 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1511 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1512 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1513 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1514 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1515 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1516 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1517 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1518 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1519 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1520 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1521 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1522 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1523 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1524 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1525 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1526 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1527 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1528 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1529 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1530 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1531 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1532 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1533 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1534 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1535 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1536 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1537 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1538 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1539 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1540 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1541 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1542 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1543 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1544 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1545 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1546 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1547 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1548 | - | 保留 |  |  | 保留区，普通HMI不使用 |
| 1549 | - | 保留 |  |  | 保留区，普通HMI不使用 |

### 1550~1829

| 地址 | 变量/宏 | 权限 | 范围 | 默认 | 含义 |
|---:|---|---|---:|---:|---|
| 1550 | PLCMonitor0 | RO |  |  | 代码宏定义参数：PLCMonitor0 |
| 1551 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移1，只读；主要复制1420~1478状态读回 |
| 1552 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移2，只读；主要复制1420~1478状态读回 |
| 1553 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移3，只读；主要复制1420~1478状态读回 |
| 1554 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移4，只读；主要复制1420~1478状态读回 |
| 1555 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移5，只读；主要复制1420~1478状态读回 |
| 1556 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移6，只读；主要复制1420~1478状态读回 |
| 1557 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移7，只读；主要复制1420~1478状态读回 |
| 1558 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移8，只读；主要复制1420~1478状态读回 |
| 1559 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移9，只读；主要复制1420~1478状态读回 |
| 1560 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移10，只读；主要复制1420~1478状态读回 |
| 1561 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移11，只读；主要复制1420~1478状态读回 |
| 1562 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移12，只读；主要复制1420~1478状态读回 |
| 1563 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移13，只读；主要复制1420~1478状态读回 |
| 1564 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移14，只读；主要复制1420~1478状态读回 |
| 1565 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移15，只读；主要复制1420~1478状态读回 |
| 1566 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移16，只读；主要复制1420~1478状态读回 |
| 1567 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移17，只读；主要复制1420~1478状态读回 |
| 1568 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移18，只读；主要复制1420~1478状态读回 |
| 1569 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移19，只读；主要复制1420~1478状态读回 |
| 1570 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移20，只读；主要复制1420~1478状态读回 |
| 1571 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移21，只读；主要复制1420~1478状态读回 |
| 1572 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移22，只读；主要复制1420~1478状态读回 |
| 1573 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移23，只读；主要复制1420~1478状态读回 |
| 1574 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移24，只读；主要复制1420~1478状态读回 |
| 1575 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移25，只读；主要复制1420~1478状态读回 |
| 1576 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移26，只读；主要复制1420~1478状态读回 |
| 1577 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移27，只读；主要复制1420~1478状态读回 |
| 1578 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移28，只读；主要复制1420~1478状态读回 |
| 1579 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移29，只读；主要复制1420~1478状态读回 |
| 1580 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移30，只读；主要复制1420~1478状态读回 |
| 1581 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移31，只读；主要复制1420~1478状态读回 |
| 1582 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移32，只读；主要复制1420~1478状态读回 |
| 1583 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移33，只读；主要复制1420~1478状态读回 |
| 1584 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移34，只读；主要复制1420~1478状态读回 |
| 1585 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移35，只读；主要复制1420~1478状态读回 |
| 1586 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移36，只读；主要复制1420~1478状态读回 |
| 1587 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移37，只读；主要复制1420~1478状态读回 |
| 1588 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移38，只读；主要复制1420~1478状态读回 |
| 1589 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移39，只读；主要复制1420~1478状态读回 |
| 1590 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移40，只读；主要复制1420~1478状态读回 |
| 1591 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移41，只读；主要复制1420~1478状态读回 |
| 1592 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移42，只读；主要复制1420~1478状态读回 |
| 1593 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移43，只读；主要复制1420~1478状态读回 |
| 1594 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移44，只读；主要复制1420~1478状态读回 |
| 1595 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移45，只读；主要复制1420~1478状态读回 |
| 1596 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移46，只读；主要复制1420~1478状态读回 |
| 1597 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移47，只读；主要复制1420~1478状态读回 |
| 1598 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移48，只读；主要复制1420~1478状态读回 |
| 1599 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移49，只读；主要复制1420~1478状态读回 |
| 1600 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移50，只读；主要复制1420~1478状态读回 |
| 1601 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移51，只读；主要复制1420~1478状态读回 |
| 1602 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移52，只读；主要复制1420~1478状态读回 |
| 1603 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移53，只读；主要复制1420~1478状态读回 |
| 1604 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移54，只读；主要复制1420~1478状态读回 |
| 1605 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移55，只读；主要复制1420~1478状态读回 |
| 1606 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移56，只读；主要复制1420~1478状态读回 |
| 1607 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移57，只读；主要复制1420~1478状态读回 |
| 1608 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移58，只读；主要复制1420~1478状态读回 |
| 1609 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移59，只读；主要复制1420~1478状态读回 |
| 1610 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移60，只读；主要复制1420~1478状态读回 |
| 1611 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移61，只读；主要复制1420~1478状态读回 |
| 1612 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移62，只读；主要复制1420~1478状态读回 |
| 1613 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移63，只读；主要复制1420~1478状态读回 |
| 1614 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移64，只读；主要复制1420~1478状态读回 |
| 1615 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移65，只读；主要复制1420~1478状态读回 |
| 1616 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移66，只读；主要复制1420~1478状态读回 |
| 1617 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移67，只读；主要复制1420~1478状态读回 |
| 1618 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移68，只读；主要复制1420~1478状态读回 |
| 1619 | - | RO |  |  | 1#模块PLCMonitor镜像，偏移69，只读；主要复制1420~1478状态读回 |
| 1620 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移0，只读；主要复制1420~1478状态读回 |
| 1621 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移1，只读；主要复制1420~1478状态读回 |
| 1622 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移2，只读；主要复制1420~1478状态读回 |
| 1623 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移3，只读；主要复制1420~1478状态读回 |
| 1624 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移4，只读；主要复制1420~1478状态读回 |
| 1625 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移5，只读；主要复制1420~1478状态读回 |
| 1626 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移6，只读；主要复制1420~1478状态读回 |
| 1627 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移7，只读；主要复制1420~1478状态读回 |
| 1628 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移8，只读；主要复制1420~1478状态读回 |
| 1629 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移9，只读；主要复制1420~1478状态读回 |
| 1630 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移10，只读；主要复制1420~1478状态读回 |
| 1631 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移11，只读；主要复制1420~1478状态读回 |
| 1632 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移12，只读；主要复制1420~1478状态读回 |
| 1633 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移13，只读；主要复制1420~1478状态读回 |
| 1634 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移14，只读；主要复制1420~1478状态读回 |
| 1635 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移15，只读；主要复制1420~1478状态读回 |
| 1636 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移16，只读；主要复制1420~1478状态读回 |
| 1637 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移17，只读；主要复制1420~1478状态读回 |
| 1638 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移18，只读；主要复制1420~1478状态读回 |
| 1639 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移19，只读；主要复制1420~1478状态读回 |
| 1640 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移20，只读；主要复制1420~1478状态读回 |
| 1641 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移21，只读；主要复制1420~1478状态读回 |
| 1642 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移22，只读；主要复制1420~1478状态读回 |
| 1643 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移23，只读；主要复制1420~1478状态读回 |
| 1644 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移24，只读；主要复制1420~1478状态读回 |
| 1645 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移25，只读；主要复制1420~1478状态读回 |
| 1646 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移26，只读；主要复制1420~1478状态读回 |
| 1647 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移27，只读；主要复制1420~1478状态读回 |
| 1648 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移28，只读；主要复制1420~1478状态读回 |
| 1649 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移29，只读；主要复制1420~1478状态读回 |
| 1650 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移30，只读；主要复制1420~1478状态读回 |
| 1651 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移31，只读；主要复制1420~1478状态读回 |
| 1652 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移32，只读；主要复制1420~1478状态读回 |
| 1653 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移33，只读；主要复制1420~1478状态读回 |
| 1654 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移34，只读；主要复制1420~1478状态读回 |
| 1655 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移35，只读；主要复制1420~1478状态读回 |
| 1656 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移36，只读；主要复制1420~1478状态读回 |
| 1657 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移37，只读；主要复制1420~1478状态读回 |
| 1658 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移38，只读；主要复制1420~1478状态读回 |
| 1659 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移39，只读；主要复制1420~1478状态读回 |
| 1660 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移40，只读；主要复制1420~1478状态读回 |
| 1661 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移41，只读；主要复制1420~1478状态读回 |
| 1662 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移42，只读；主要复制1420~1478状态读回 |
| 1663 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移43，只读；主要复制1420~1478状态读回 |
| 1664 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移44，只读；主要复制1420~1478状态读回 |
| 1665 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移45，只读；主要复制1420~1478状态读回 |
| 1666 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移46，只读；主要复制1420~1478状态读回 |
| 1667 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移47，只读；主要复制1420~1478状态读回 |
| 1668 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移48，只读；主要复制1420~1478状态读回 |
| 1669 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移49，只读；主要复制1420~1478状态读回 |
| 1670 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移50，只读；主要复制1420~1478状态读回 |
| 1671 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移51，只读；主要复制1420~1478状态读回 |
| 1672 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移52，只读；主要复制1420~1478状态读回 |
| 1673 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移53，只读；主要复制1420~1478状态读回 |
| 1674 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移54，只读；主要复制1420~1478状态读回 |
| 1675 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移55，只读；主要复制1420~1478状态读回 |
| 1676 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移56，只读；主要复制1420~1478状态读回 |
| 1677 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移57，只读；主要复制1420~1478状态读回 |
| 1678 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移58，只读；主要复制1420~1478状态读回 |
| 1679 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移59，只读；主要复制1420~1478状态读回 |
| 1680 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移60，只读；主要复制1420~1478状态读回 |
| 1681 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移61，只读；主要复制1420~1478状态读回 |
| 1682 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移62，只读；主要复制1420~1478状态读回 |
| 1683 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移63，只读；主要复制1420~1478状态读回 |
| 1684 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移64，只读；主要复制1420~1478状态读回 |
| 1685 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移65，只读；主要复制1420~1478状态读回 |
| 1686 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移66，只读；主要复制1420~1478状态读回 |
| 1687 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移67，只读；主要复制1420~1478状态读回 |
| 1688 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移68，只读；主要复制1420~1478状态读回 |
| 1689 | - | RO |  |  | 2#模块PLCMonitor镜像，偏移69，只读；主要复制1420~1478状态读回 |
| 1690 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移0，只读；主要复制1420~1478状态读回 |
| 1691 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移1，只读；主要复制1420~1478状态读回 |
| 1692 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移2，只读；主要复制1420~1478状态读回 |
| 1693 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移3，只读；主要复制1420~1478状态读回 |
| 1694 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移4，只读；主要复制1420~1478状态读回 |
| 1695 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移5，只读；主要复制1420~1478状态读回 |
| 1696 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移6，只读；主要复制1420~1478状态读回 |
| 1697 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移7，只读；主要复制1420~1478状态读回 |
| 1698 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移8，只读；主要复制1420~1478状态读回 |
| 1699 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移9，只读；主要复制1420~1478状态读回 |
| 1700 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移10，只读；主要复制1420~1478状态读回 |
| 1701 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移11，只读；主要复制1420~1478状态读回 |
| 1702 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移12，只读；主要复制1420~1478状态读回 |
| 1703 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移13，只读；主要复制1420~1478状态读回 |
| 1704 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移14，只读；主要复制1420~1478状态读回 |
| 1705 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移15，只读；主要复制1420~1478状态读回 |
| 1706 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移16，只读；主要复制1420~1478状态读回 |
| 1707 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移17，只读；主要复制1420~1478状态读回 |
| 1708 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移18，只读；主要复制1420~1478状态读回 |
| 1709 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移19，只读；主要复制1420~1478状态读回 |
| 1710 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移20，只读；主要复制1420~1478状态读回 |
| 1711 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移21，只读；主要复制1420~1478状态读回 |
| 1712 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移22，只读；主要复制1420~1478状态读回 |
| 1713 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移23，只读；主要复制1420~1478状态读回 |
| 1714 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移24，只读；主要复制1420~1478状态读回 |
| 1715 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移25，只读；主要复制1420~1478状态读回 |
| 1716 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移26，只读；主要复制1420~1478状态读回 |
| 1717 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移27，只读；主要复制1420~1478状态读回 |
| 1718 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移28，只读；主要复制1420~1478状态读回 |
| 1719 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移29，只读；主要复制1420~1478状态读回 |
| 1720 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移30，只读；主要复制1420~1478状态读回 |
| 1721 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移31，只读；主要复制1420~1478状态读回 |
| 1722 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移32，只读；主要复制1420~1478状态读回 |
| 1723 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移33，只读；主要复制1420~1478状态读回 |
| 1724 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移34，只读；主要复制1420~1478状态读回 |
| 1725 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移35，只读；主要复制1420~1478状态读回 |
| 1726 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移36，只读；主要复制1420~1478状态读回 |
| 1727 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移37，只读；主要复制1420~1478状态读回 |
| 1728 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移38，只读；主要复制1420~1478状态读回 |
| 1729 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移39，只读；主要复制1420~1478状态读回 |
| 1730 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移40，只读；主要复制1420~1478状态读回 |
| 1731 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移41，只读；主要复制1420~1478状态读回 |
| 1732 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移42，只读；主要复制1420~1478状态读回 |
| 1733 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移43，只读；主要复制1420~1478状态读回 |
| 1734 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移44，只读；主要复制1420~1478状态读回 |
| 1735 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移45，只读；主要复制1420~1478状态读回 |
| 1736 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移46，只读；主要复制1420~1478状态读回 |
| 1737 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移47，只读；主要复制1420~1478状态读回 |
| 1738 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移48，只读；主要复制1420~1478状态读回 |
| 1739 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移49，只读；主要复制1420~1478状态读回 |
| 1740 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移50，只读；主要复制1420~1478状态读回 |
| 1741 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移51，只读；主要复制1420~1478状态读回 |
| 1742 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移52，只读；主要复制1420~1478状态读回 |
| 1743 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移53，只读；主要复制1420~1478状态读回 |
| 1744 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移54，只读；主要复制1420~1478状态读回 |
| 1745 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移55，只读；主要复制1420~1478状态读回 |
| 1746 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移56，只读；主要复制1420~1478状态读回 |
| 1747 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移57，只读；主要复制1420~1478状态读回 |
| 1748 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移58，只读；主要复制1420~1478状态读回 |
| 1749 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移59，只读；主要复制1420~1478状态读回 |
| 1750 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移60，只读；主要复制1420~1478状态读回 |
| 1751 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移61，只读；主要复制1420~1478状态读回 |
| 1752 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移62，只读；主要复制1420~1478状态读回 |
| 1753 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移63，只读；主要复制1420~1478状态读回 |
| 1754 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移64，只读；主要复制1420~1478状态读回 |
| 1755 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移65，只读；主要复制1420~1478状态读回 |
| 1756 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移66，只读；主要复制1420~1478状态读回 |
| 1757 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移67，只读；主要复制1420~1478状态读回 |
| 1758 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移68，只读；主要复制1420~1478状态读回 |
| 1759 | - | RO |  |  | 3#模块PLCMonitor镜像，偏移69，只读；主要复制1420~1478状态读回 |
| 1760 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移0，只读；主要复制1420~1478状态读回 |
| 1761 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移1，只读；主要复制1420~1478状态读回 |
| 1762 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移2，只读；主要复制1420~1478状态读回 |
| 1763 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移3，只读；主要复制1420~1478状态读回 |
| 1764 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移4，只读；主要复制1420~1478状态读回 |
| 1765 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移5，只读；主要复制1420~1478状态读回 |
| 1766 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移6，只读；主要复制1420~1478状态读回 |
| 1767 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移7，只读；主要复制1420~1478状态读回 |
| 1768 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移8，只读；主要复制1420~1478状态读回 |
| 1769 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移9，只读；主要复制1420~1478状态读回 |
| 1770 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移10，只读；主要复制1420~1478状态读回 |
| 1771 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移11，只读；主要复制1420~1478状态读回 |
| 1772 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移12，只读；主要复制1420~1478状态读回 |
| 1773 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移13，只读；主要复制1420~1478状态读回 |
| 1774 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移14，只读；主要复制1420~1478状态读回 |
| 1775 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移15，只读；主要复制1420~1478状态读回 |
| 1776 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移16，只读；主要复制1420~1478状态读回 |
| 1777 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移17，只读；主要复制1420~1478状态读回 |
| 1778 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移18，只读；主要复制1420~1478状态读回 |
| 1779 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移19，只读；主要复制1420~1478状态读回 |
| 1780 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移20，只读；主要复制1420~1478状态读回 |
| 1781 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移21，只读；主要复制1420~1478状态读回 |
| 1782 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移22，只读；主要复制1420~1478状态读回 |
| 1783 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移23，只读；主要复制1420~1478状态读回 |
| 1784 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移24，只读；主要复制1420~1478状态读回 |
| 1785 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移25，只读；主要复制1420~1478状态读回 |
| 1786 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移26，只读；主要复制1420~1478状态读回 |
| 1787 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移27，只读；主要复制1420~1478状态读回 |
| 1788 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移28，只读；主要复制1420~1478状态读回 |
| 1789 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移29，只读；主要复制1420~1478状态读回 |
| 1790 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移30，只读；主要复制1420~1478状态读回 |
| 1791 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移31，只读；主要复制1420~1478状态读回 |
| 1792 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移32，只读；主要复制1420~1478状态读回 |
| 1793 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移33，只读；主要复制1420~1478状态读回 |
| 1794 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移34，只读；主要复制1420~1478状态读回 |
| 1795 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移35，只读；主要复制1420~1478状态读回 |
| 1796 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移36，只读；主要复制1420~1478状态读回 |
| 1797 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移37，只读；主要复制1420~1478状态读回 |
| 1798 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移38，只读；主要复制1420~1478状态读回 |
| 1799 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移39，只读；主要复制1420~1478状态读回 |
| 1800 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移40，只读；主要复制1420~1478状态读回 |
| 1801 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移41，只读；主要复制1420~1478状态读回 |
| 1802 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移42，只读；主要复制1420~1478状态读回 |
| 1803 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移43，只读；主要复制1420~1478状态读回 |
| 1804 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移44，只读；主要复制1420~1478状态读回 |
| 1805 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移45，只读；主要复制1420~1478状态读回 |
| 1806 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移46，只读；主要复制1420~1478状态读回 |
| 1807 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移47，只读；主要复制1420~1478状态读回 |
| 1808 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移48，只读；主要复制1420~1478状态读回 |
| 1809 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移49，只读；主要复制1420~1478状态读回 |
| 1810 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移50，只读；主要复制1420~1478状态读回 |
| 1811 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移51，只读；主要复制1420~1478状态读回 |
| 1812 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移52，只读；主要复制1420~1478状态读回 |
| 1813 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移53，只读；主要复制1420~1478状态读回 |
| 1814 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移54，只读；主要复制1420~1478状态读回 |
| 1815 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移55，只读；主要复制1420~1478状态读回 |
| 1816 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移56，只读；主要复制1420~1478状态读回 |
| 1817 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移57，只读；主要复制1420~1478状态读回 |
| 1818 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移58，只读；主要复制1420~1478状态读回 |
| 1819 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移59，只读；主要复制1420~1478状态读回 |
| 1820 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移60，只读；主要复制1420~1478状态读回 |
| 1821 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移61，只读；主要复制1420~1478状态读回 |
| 1822 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移62，只读；主要复制1420~1478状态读回 |
| 1823 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移63，只读；主要复制1420~1478状态读回 |
| 1824 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移64，只读；主要复制1420~1478状态读回 |
| 1825 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移65，只读；主要复制1420~1478状态读回 |
| 1826 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移66，只读；主要复制1420~1478状态读回 |
| 1827 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移67，只读；主要复制1420~1478状态读回 |
| 1828 | - | RO |  |  | 4#模块PLCMonitor镜像，偏移68，只读；主要复制1420~1478状态读回 |
| 1829 | PLCMonitor279 | RO |  |  | 代码宏定义参数：PLCMonitor279 |

### 1830~1999

| 地址 | 变量/宏 | 权限 | 范围 | 默认 | 含义 |
|---:|---|---|---:|---:|---|
| 1830 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移0，对应316 Parameter[165]，经330转发写入 |
| 1831 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移1，对应316 Parameter[166]，经330转发写入 |
| 1832 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移2，对应316 Parameter[167]，经330转发写入 |
| 1833 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移3，对应316 Parameter[168]，经330转发写入 |
| 1834 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移4，对应316 Parameter[169]，经330转发写入 |
| 1835 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移5，对应316 Parameter[170]，经330转发写入 |
| 1836 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移6，对应316 Parameter[171]，经330转发写入 |
| 1837 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移7，对应316 Parameter[172]，经330转发写入 |
| 1838 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移8，对应316 Parameter[173]，经330转发写入 |
| 1839 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移9，对应316 Parameter[174]，经330转发写入 |
| 1840 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移10，对应316 Parameter[175]，经330转发写入 |
| 1841 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移11，对应316 Parameter[176]，经330转发写入 |
| 1842 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移12，对应316 Parameter[177]，经330转发写入 |
| 1843 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移13，对应316 Parameter[178]，经330转发写入 |
| 1844 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移14，对应316 Parameter[179]，经330转发写入 |
| 1845 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移15，对应316 Parameter[180]，经330转发写入 |
| 1846 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移16，对应316 Parameter[181]，经330转发写入 |
| 1847 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移17，对应316 Parameter[182]，经330转发写入 |
| 1848 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移18，对应316 Parameter[183]，经330转发写入 |
| 1849 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移19，对应316 Parameter[184]，经330转发写入 |
| 1850 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移20，对应316 Parameter[185]，经330转发写入 |
| 1851 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移21，对应316 Parameter[186]，经330转发写入 |
| 1852 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移22，对应316 Parameter[187]，经330转发写入 |
| 1853 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移23，对应316 Parameter[188]，经330转发写入 |
| 1854 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移24，对应316 Parameter[189]，经330转发写入 |
| 1855 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移25，对应316 Parameter[190]，经330转发写入 |
| 1856 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移26，对应316 Parameter[191]，经330转发写入 |
| 1857 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移27，对应316 Parameter[192]，经330转发写入 |
| 1858 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移28，对应316 Parameter[193]，经330转发写入 |
| 1859 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移29，对应316 Parameter[194]，经330转发写入 |
| 1860 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移30，对应316 Parameter[195]，经330转发写入 |
| 1861 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移31，对应316 Parameter[196]，经330转发写入 |
| 1862 | - | RW(网关) |  |  | PSC316外机1#网关设定镜像，偏移32，对应316 Parameter[197]，经330转发写入 |
| 1863 | - | RO |  |  | PSC316外机1#网关诊断/状态，偏移33，只读 |
| 1864 | - | RO |  |  | PSC316外机1#网关诊断/状态，偏移34，只读 |
| 1865 | - | RO |  |  | PSC316外机1#网关诊断/状态，偏移35，只读 |
| 1866 | - | RO |  |  | PSC316外机1#网关诊断/状态，偏移36，只读 |
| 1867 | - | RO |  |  | PSC316外机1#网关诊断/状态，偏移37，只读 |
| 1868 | - | RO |  |  | PSC316外机1#网关诊断/状态，偏移38，只读 |
| 1869 | - | RO |  |  | PSC316外机1#网关诊断/状态，偏移39，只读 |
| 1870 | - | RO |  |  | PSC316外机1#网关诊断/状态，偏移40，只读 |
| 1871 | PSC316_1_CompChoice | RW(网关) | 0..3 | 3 | 1#外机316 Parameter[38] CompChoice：0定频，1老蓝海华腾协议，2汇川，3施耐德ATV610；现场ATV610写3 |
| 1872 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移0，对应316 Parameter[165]，经330转发写入 |
| 1873 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移1，对应316 Parameter[166]，经330转发写入 |
| 1874 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移2，对应316 Parameter[167]，经330转发写入 |
| 1875 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移3，对应316 Parameter[168]，经330转发写入 |
| 1876 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移4，对应316 Parameter[169]，经330转发写入 |
| 1877 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移5，对应316 Parameter[170]，经330转发写入 |
| 1878 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移6，对应316 Parameter[171]，经330转发写入 |
| 1879 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移7，对应316 Parameter[172]，经330转发写入 |
| 1880 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移8，对应316 Parameter[173]，经330转发写入 |
| 1881 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移9，对应316 Parameter[174]，经330转发写入 |
| 1882 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移10，对应316 Parameter[175]，经330转发写入 |
| 1883 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移11，对应316 Parameter[176]，经330转发写入 |
| 1884 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移12，对应316 Parameter[177]，经330转发写入 |
| 1885 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移13，对应316 Parameter[178]，经330转发写入 |
| 1886 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移14，对应316 Parameter[179]，经330转发写入 |
| 1887 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移15，对应316 Parameter[180]，经330转发写入 |
| 1888 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移16，对应316 Parameter[181]，经330转发写入 |
| 1889 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移17，对应316 Parameter[182]，经330转发写入 |
| 1890 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移18，对应316 Parameter[183]，经330转发写入 |
| 1891 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移19，对应316 Parameter[184]，经330转发写入 |
| 1892 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移20，对应316 Parameter[185]，经330转发写入 |
| 1893 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移21，对应316 Parameter[186]，经330转发写入 |
| 1894 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移22，对应316 Parameter[187]，经330转发写入 |
| 1895 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移23，对应316 Parameter[188]，经330转发写入 |
| 1896 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移24，对应316 Parameter[189]，经330转发写入 |
| 1897 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移25，对应316 Parameter[190]，经330转发写入 |
| 1898 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移26，对应316 Parameter[191]，经330转发写入 |
| 1899 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移27，对应316 Parameter[192]，经330转发写入 |
| 1900 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移28，对应316 Parameter[193]，经330转发写入 |
| 1901 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移29，对应316 Parameter[194]，经330转发写入 |
| 1902 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移30，对应316 Parameter[195]，经330转发写入 |
| 1903 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移31，对应316 Parameter[196]，经330转发写入 |
| 1904 | - | RW(网关) |  |  | PSC316外机2#网关设定镜像，偏移32，对应316 Parameter[197]，经330转发写入 |
| 1905 | - | RO |  |  | PSC316外机2#网关诊断/状态，偏移33，只读 |
| 1906 | - | RO |  |  | PSC316外机2#网关诊断/状态，偏移34，只读 |
| 1907 | - | RO |  |  | PSC316外机2#网关诊断/状态，偏移35，只读 |
| 1908 | - | RO |  |  | PSC316外机2#网关诊断/状态，偏移36，只读 |
| 1909 | - | RO |  |  | PSC316外机2#网关诊断/状态，偏移37，只读 |
| 1910 | - | RO |  |  | PSC316外机2#网关诊断/状态，偏移38，只读 |
| 1911 | - | RO |  |  | PSC316外机2#网关诊断/状态，偏移39，只读 |
| 1912 | - | RO |  |  | PSC316外机2#网关诊断/状态，偏移40，只读 |
| 1913 | PSC316_2_CompChoice | RW(网关) | 0..3 | 3 | 2#外机316 Parameter[38] CompChoice：0定频，1老蓝海华腾协议，2汇川，3施耐德ATV610；现场ATV610写3 |
| 1914 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移0，对应316 Parameter[165]，经330转发写入 |
| 1915 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移1，对应316 Parameter[166]，经330转发写入 |
| 1916 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移2，对应316 Parameter[167]，经330转发写入 |
| 1917 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移3，对应316 Parameter[168]，经330转发写入 |
| 1918 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移4，对应316 Parameter[169]，经330转发写入 |
| 1919 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移5，对应316 Parameter[170]，经330转发写入 |
| 1920 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移6，对应316 Parameter[171]，经330转发写入 |
| 1921 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移7，对应316 Parameter[172]，经330转发写入 |
| 1922 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移8，对应316 Parameter[173]，经330转发写入 |
| 1923 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移9，对应316 Parameter[174]，经330转发写入 |
| 1924 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移10，对应316 Parameter[175]，经330转发写入 |
| 1925 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移11，对应316 Parameter[176]，经330转发写入 |
| 1926 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移12，对应316 Parameter[177]，经330转发写入 |
| 1927 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移13，对应316 Parameter[178]，经330转发写入 |
| 1928 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移14，对应316 Parameter[179]，经330转发写入 |
| 1929 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移15，对应316 Parameter[180]，经330转发写入 |
| 1930 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移16，对应316 Parameter[181]，经330转发写入 |
| 1931 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移17，对应316 Parameter[182]，经330转发写入 |
| 1932 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移18，对应316 Parameter[183]，经330转发写入 |
| 1933 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移19，对应316 Parameter[184]，经330转发写入 |
| 1934 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移20，对应316 Parameter[185]，经330转发写入 |
| 1935 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移21，对应316 Parameter[186]，经330转发写入 |
| 1936 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移22，对应316 Parameter[187]，经330转发写入 |
| 1937 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移23，对应316 Parameter[188]，经330转发写入 |
| 1938 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移24，对应316 Parameter[189]，经330转发写入 |
| 1939 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移25，对应316 Parameter[190]，经330转发写入 |
| 1940 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移26，对应316 Parameter[191]，经330转发写入 |
| 1941 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移27，对应316 Parameter[192]，经330转发写入 |
| 1942 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移28，对应316 Parameter[193]，经330转发写入 |
| 1943 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移29，对应316 Parameter[194]，经330转发写入 |
| 1944 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移30，对应316 Parameter[195]，经330转发写入 |
| 1945 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移31，对应316 Parameter[196]，经330转发写入 |
| 1946 | - | RW(网关) |  |  | PSC316外机3#网关设定镜像，偏移32，对应316 Parameter[197]，经330转发写入 |
| 1947 | - | RO |  |  | PSC316外机3#网关诊断/状态，偏移33，只读 |
| 1948 | - | RO |  |  | PSC316外机3#网关诊断/状态，偏移34，只读 |
| 1949 | - | RO |  |  | PSC316外机3#网关诊断/状态，偏移35，只读 |
| 1950 | - | RO |  |  | PSC316外机3#网关诊断/状态，偏移36，只读 |
| 1951 | - | RO |  |  | PSC316外机3#网关诊断/状态，偏移37，只读 |
| 1952 | - | RO |  |  | PSC316外机3#网关诊断/状态，偏移38，只读 |
| 1953 | - | RO |  |  | PSC316外机3#网关诊断/状态，偏移39，只读 |
| 1954 | - | RO |  |  | PSC316外机3#网关诊断/状态，偏移40，只读 |
| 1955 | PSC316_3_CompChoice | RW(网关) | 0..3 | 3 | 3#外机316 Parameter[38] CompChoice：0定频，1老蓝海华腾协议，2汇川，3施耐德ATV610；现场ATV610写3 |
| 1956 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移0，对应316 Parameter[165]，经330转发写入 |
| 1957 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移1，对应316 Parameter[166]，经330转发写入 |
| 1958 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移2，对应316 Parameter[167]，经330转发写入 |
| 1959 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移3，对应316 Parameter[168]，经330转发写入 |
| 1960 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移4，对应316 Parameter[169]，经330转发写入 |
| 1961 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移5，对应316 Parameter[170]，经330转发写入 |
| 1962 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移6，对应316 Parameter[171]，经330转发写入 |
| 1963 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移7，对应316 Parameter[172]，经330转发写入 |
| 1964 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移8，对应316 Parameter[173]，经330转发写入 |
| 1965 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移9，对应316 Parameter[174]，经330转发写入 |
| 1966 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移10，对应316 Parameter[175]，经330转发写入 |
| 1967 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移11，对应316 Parameter[176]，经330转发写入 |
| 1968 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移12，对应316 Parameter[177]，经330转发写入 |
| 1969 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移13，对应316 Parameter[178]，经330转发写入 |
| 1970 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移14，对应316 Parameter[179]，经330转发写入 |
| 1971 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移15，对应316 Parameter[180]，经330转发写入 |
| 1972 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移16，对应316 Parameter[181]，经330转发写入 |
| 1973 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移17，对应316 Parameter[182]，经330转发写入 |
| 1974 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移18，对应316 Parameter[183]，经330转发写入 |
| 1975 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移19，对应316 Parameter[184]，经330转发写入 |
| 1976 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移20，对应316 Parameter[185]，经330转发写入 |
| 1977 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移21，对应316 Parameter[186]，经330转发写入 |
| 1978 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移22，对应316 Parameter[187]，经330转发写入 |
| 1979 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移23，对应316 Parameter[188]，经330转发写入 |
| 1980 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移24，对应316 Parameter[189]，经330转发写入 |
| 1981 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移25，对应316 Parameter[190]，经330转发写入 |
| 1982 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移26，对应316 Parameter[191]，经330转发写入 |
| 1983 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移27，对应316 Parameter[192]，经330转发写入 |
| 1984 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移28，对应316 Parameter[193]，经330转发写入 |
| 1985 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移29，对应316 Parameter[194]，经330转发写入 |
| 1986 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移30，对应316 Parameter[195]，经330转发写入 |
| 1987 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移31，对应316 Parameter[196]，经330转发写入 |
| 1988 | - | RW(网关) |  |  | PSC316外机4#网关设定镜像，偏移32，对应316 Parameter[197]，经330转发写入 |
| 1989 | - | RO |  |  | PSC316外机4#网关诊断/状态，偏移33，只读 |
| 1990 | - | RO |  |  | PSC316外机4#网关诊断/状态，偏移34，只读 |
| 1991 | - | RO |  |  | PSC316外机4#网关诊断/状态，偏移35，只读 |
| 1992 | - | RO |  |  | PSC316外机4#网关诊断/状态，偏移36，只读 |
| 1993 | - | RO |  |  | PSC316外机4#网关诊断/状态，偏移37，只读 |
| 1994 | - | RO |  |  | PSC316外机4#网关诊断/状态，偏移38，只读 |
| 1995 | - | RO |  |  | PSC316外机4#网关诊断/状态，偏移39，只读 |
| 1996 | - | RO |  |  | PSC316外机4#网关诊断/状态，偏移40，只读 |
| 1997 | PSC316_4_CompChoice | RW(网关) | 0..3 | 3 | 4#外机316 Parameter[38] CompChoice：0定频，1老蓝海华腾协议，2汇川，3施耐德ATV610；现场ATV610写3 |
| 1998 | - | 保留 |  |  | 保留地址，普通HMI不使用 |
| 1999 | - | 保留 |  |  | 保留地址，普通HMI不使用 |

## 6. Pcoil 线圈地址

| Pcoil地址 | 权限 | 含义 |
|---:|---|---|
| 4 | RW | HMI开放写线圈，具体功能看页面逻辑 |
| 5 | RW | HMI开放写线圈，具体功能看页面逻辑 |
| 6 | RW | HMI开放写线圈，具体功能看页面逻辑 |
| 50 | RW | HMI开放写线圈，具体功能看页面逻辑 |
| 51 | RW | HMI开放写线圈，具体功能看页面逻辑 |
| 100~128 | RO | 594~622 故障镜像 |
| 128 | RW | 代码白名单允许写，同时也处于故障镜像范围，HMI使用需谨慎 |
| 135~142 | RO | 640~647 A/B/C/D蒸发低温保护镜像 |
| 143~146 | RO | 623~626 C/D蒸发温度故障镜像 |
| 147 | RO | 627 AI0房间压差故障镜像 |



