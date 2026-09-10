# MCGSPro维护提醒、定时开关机与AI/NTC校准实施说明

整理日期：2026年9月7日

适用固件：

- PSC330RK-V10室内机
- PSC316RK-V12室外机
- MCGSPro通过A0/B0连接PSC330，PSC316参数经PSC330网关访问

本文使用0基Modbus地址。MCGSPro设备驱动必须与固件地址方式一致。正式制作前，先用一个已知只读点核对一次地址是否偏移1位。

## 1. 总体画面建议

建立四个维护页面：

1. `维护保养`
   - 维护提醒使能
   - 保养间隔小时
   - 本周期已运行小时
   - 剩余小时/超期小时
   - 稍后提醒
   - 保养完成并复位

2. `周定时`
   - 总使能
   - 星期一至星期日
   - 每天两个运行时段
   - 当前RTC时间、当前定时目标、当前系统步骤
   - 退出定时、停机并退出定时

3. `PSC330校准`
   - AI0至AI4
   - NTC0至NTC11
   - 当前值、标准值、原偏移、计算后偏移
   - 计算、写入、写入结果、保存等待状态

4. `PSC316校准`
   - 1至4号外机独立页签
   - AI0至AI3压力
   - NTC0至NTC7温度
   - 在线状态、网关写状态、错误码
   - 当前值、标准值、原偏移、计算后偏移

校准页面应增加工程权限。校准时建议机组完全停机、传感器稳定，并禁止多人同时写参数。

## 2. MCGS变量命名和类型

规则：

- `Rxxxx_...`：设备连接变量。
- `n...`：MCGS本地整数变量。
- `d...`：MCGS本地浮点变量。
- `b...`：MCGS本地0/1变量。
- 周定时设置、本地维护暂缓时间应设置为掉电保持。
- 写入检查计数、忙状态、临时计算值不需要掉电保持。

Modbus数据类型：

- 普通开关、小时、状态：`WUB`，无符号16位。
- AI/NTC校准偏移：`WB`，有符号16位，必须支持负数。

不要只根据`!SetDevice`返回值判定参数已经保存。必须依次区分：

1. MCGS已发出写命令。
2. 设备接受写入。
3. 目标寄存器读回等于写入值。
4. EEPROM写入完成并经过真实断电重启验证。

## 3. 维护提醒

### 3.1 PSC330寄存器

| 地址 | 连接变量建议名 | 含义 | 范围 |
|---:|---|---|---|
| 362 | `R0362_维护提醒使能` | 0关闭，1启用 | 0..1 |
| 363 | `R0363_保养间隔小时` | 运行时间达到该值后提醒；0不提醒 | 0..30000 |
| 364 | `R0364_保养复位命令` | 写1复位，固件执行后自动清0 | 0..1 |
| 373 | `R0373_保养累计运行小时` | 自上次复位后的实际运行小时 | 0..30000 |
| 894 | `R0894_维护提醒状态` | 0未到期，1已到期 | 只读 |

PSC330只在`SysStep=2`正常运行时累计373。提醒条件为：

```text
R0362_维护提醒使能 = 1
并且 R0363_保养间隔小时 > 0
并且 R0373_保养累计运行小时 >= R0363_保养间隔小时
```

维护到期只报警提醒，不会自动停机。

### 3.2 本地变量

| 变量 | 类型 | 保持 | 用途 |
|---|---|---|---|
| `bMaintenancePopup` | 整数/布尔 | 否 | 提醒遮罩或弹窗可见条件 |
| `nMaintenanceSnoozeSec` | 32位整数 | 是 | 稍后提醒剩余秒数 |
| `nMaintenanceResetCheck` | 整数 | 否 | 复位结果监视使能 |
| `nMaintenanceResetTimeout` | 整数 | 否 | 复位超时计数 |
| `nMaintenanceWriteRet` | 整数 | 否 | `WriteP`返回诊断值 |
| `nMaintenanceResult` | 整数 | 否 | 0空闲，1处理中，2成功，101超时 |
| `nWriteOne` | 整数 | 否 | 固定值1 |

### 3.3 周期脚本

设置为1秒周期：

```text
'维护提醒显示和稍后提醒倒计时
If R0894_维护提醒状态 = 0 Then
    bMaintenancePopup = 0
    nMaintenanceSnoozeSec = 0
Else
    If nMaintenanceSnoozeSec > 0 Then
        nMaintenanceSnoozeSec = nMaintenanceSnoozeSec - 1
        bMaintenancePopup = 0
    Else
        bMaintenancePopup = 1
    EndIf
EndIf
```

将一个全屏半透明遮罩组或维护提醒窗口的可见性绑定到`bMaintenancePopup=1`。这样不依赖不同MCGSPro版本的弹窗函数。

剩余时间显示：

```text
If R0363_保养间隔小时 > R0373_保养累计运行小时 Then
    nMaintenanceRemainHour = R0363_保养间隔小时 - R0373_保养累计运行小时
    nMaintenanceOverdueHour = 0
Else
    nMaintenanceRemainHour = 0
    nMaintenanceOverdueHour = R0373_保养累计运行小时 - R0363_保养间隔小时
EndIf
```

### 3.4 按钮脚本

“稍后提醒4小时”：

```text
nMaintenanceSnoozeSec = 14400
bMaintenancePopup = 0
```

这只隐藏MCGS本地提示，不会清除PSC330的894提醒位。

“保养完成”必须先弹出确认窗口，确认按钮执行：

```text
nWriteOne = 1
nMaintenanceResult = 1
nMaintenanceResetCheck = 1
nMaintenanceResetTimeout = 0
!SetDevice(设备0,6,"WriteP(4,364,WUB,1,nWriteOne,nMaintenanceWriteRet)")
```

设置200ms周期的复位监视脚本：

```text
If nMaintenanceResetCheck <> 1 Then
    Exit
EndIf

nMaintenanceResetTimeout = nMaintenanceResetTimeout + 1

If R0364_保养复位命令 = 0 Then
    If R0373_保养累计运行小时 = 0 Then
        If R0894_维护提醒状态 = 0 Then
            nMaintenanceResult = 2
            nMaintenanceResetCheck = 0
            nMaintenanceSnoozeSec = 0
            bMaintenancePopup = 0
            Exit
        EndIf
    EndIf
EndIf

'10秒超时
If nMaintenanceResetTimeout >= 50 Then
    nMaintenanceResult = 101
    nMaintenanceResetCheck = 0
EndIf
```

## 4. 周定时开关机（旧版单时段草稿，停止使用）

> 2026年9月8日更正：本章旧版只展开了“星期一第1时段”，并且把165误称为“PLC控制方式”，不再作为现场实施依据。完整的周一至周日、每天两个时段脚本和逐步操作说明，请使用同目录下的`MCGSPro周定时开关机_周一至周日完整实施说明.md`、`MCGSPro周定时_全周14时段循环脚本.txt`和`MCGSPro周定时_全周按钮脚本.txt`。
>
> 正确含义：163=普通控制来源（0本地、1远程、2 PLC）；165=定时模式使能（0普通、1定时）；714=当前实际控制方式（3表示定时）；1388=定时运行目标。进入周定时后163保持原值是正常现象。

本章按“完全没有用过MCGSPro脚本”的情况编写。不要一开始就建立全周14个时段，先严格按照4.1至4.10完成“星期一第1时段”，确认它能自动开机和停机后，再按4.11复制成全周计划。

### 4.1 先理解这个功能控制什么

周定时不是直接控制Y点，也不是直接控制风机、压缩机。MCGSPro只向PSC330写两个命令：

| 地址 | MCGS连接变量 | 作用 |
|---:|---|---|
| 165 | `R0165_开关机控制方式` | 写1进入定时控制，写0退出定时控制 |
| 1388 | `R1388_定时运行目标` | 定时模式中，写1要求运行，写0要求停机 |

以下三个寄存器只用来显示和判断结果：

| 地址 | MCGS连接变量 | 作用 |
|---:|---|---|
| 700 | `R0700_系统状态` | 显示PSC330当前系统状态 |
| 709 | `R0709_开关机步骤` | 0完全停机，1启动过程，2正常运行，3/4/5停机过程 |
| 710 | `R0710_故障停机状态` | 0表示当前没有故障停机条件 |

工作过程如下：

1. 到达计划开始时间，MCGS把1388写成1。
2. PSC330在允许启动时，709由0变为1，完成开机后变为2。
3. 到达计划结束时间，MCGS把1388写成0。
4. PSC330按通风、制冷或制热的正常关机顺序停机，709经过停机步骤后回到0。

不要使用`R0398_HMI开关机命令`做周定时。398是普通手动开关机命令，定时模式应只使用165和1388，否则两个控制来源会互相冲突。

### 4.2 第一步：备份当前MCGS工程

1. 在MCGSPro顶部菜单点`文件`。
2. 点`工程另存为`。
3. 另存为一个新文件，例如`TEST_增加周定时_20260908.MCP`。
4. 后面只修改这个副本，不要直接覆盖唯一可用的现场工程。

### 4.3 第二步：检查5个PSC330连接变量

如果工程中已经有下面5个以`R`开头的连接变量，不要重复创建，只检查它们能够正常显示。

```text
R0165_开关机控制方式
R1388_定时运行目标
R0700_系统状态
R0709_开关机步骤
R0710_故障停机状态
```

检查方法：

1. 在工程左侧工作台找到`实时数据库`并双击。
2. 在变量列表中搜索`R0165`、`R1388`、`R0700`、`R0709`和`R0710`。
3. 确认它们是连接PSC330的设备变量，不是只有名字但没有设备通道的本地变量。
4. 双击变量检查设备连接。当前工程使用0基地址时，地址分别为165、1388、700、709、710，数据为16位无符号整数。
5. 先运行工程观察709。如果监控软件中的709变化，而MCGS里的`R0709_开关机步骤`始终不变，说明设备变量连接不正确，先不要继续做定时。

本文脚本中的设备名写成`设备0`。如果工程设备窗口中的实际名称不是`设备0`，必须把全部`!SetDevice(设备0,...)`中的`设备0`替换成实际设备名。

### 4.4 第三步：创建本地变量

#### 4.4.1 打开变量创建位置

1. 在工程左侧工作台双击`实时数据库`。
2. 在实时数据库窗口空白处点鼠标右键。
3. 选择`新增对象`或工具栏上的`新增对象`按钮。
4. 每次输入一个变量名。
5. 本章中的“整数变量”在MCGSPro中统一选择`数值型`，初值填0。
6. 本章中的“字符串变量”选择`字符型`，字符串长度设为32。

不要把下面这些本地变量连接到`设备0`。它们只在触摸屏内部使用。

#### 4.4.2 必须掉电保存的变量

下面6个变量要勾选`存盘`、`掉电保持`或同等含义的选项。不同MCGSPro版本名称可能略有差异，目的都是触摸屏重启后保留设置。

| 变量名 | 类型 | 初值 | 含义 |
|---|---|---:|---|
| `bScheduleMasterEnable` | 数值型 | 0 | 本地周定时总使能，0停用，1启用 |
| `bMon1Enable` | 数值型 | 0 | 星期一第1时段是否启用 |
| `nMon1StartHour` | 数值型 | 8 | 开始小时，0至23 |
| `nMon1StartMin` | 数值型 | 0 | 开始分钟，0至59 |
| `nMon1EndHour` | 数值型 | 18 | 结束小时，0至23 |
| `nMon1EndMin` | 数值型 | 0 | 结束分钟，0至59 |

#### 4.4.3 不需要掉电保存的计算变量

下面变量全部是MCGS内部计算或诊断变量，不勾选掉电保持：

| 变量名 | 类型 | 初值 | 含义 |
|---|---|---:|---|
| `iScheduleNow` | 数值型 | 0 | 当前时间的整数值 |
| `nRTCWeek` | 数值型 | 0 | 当前星期，1为星期一，7为星期日 |
| `nRTCHour` | 数值型 | 0 | 当前小时 |
| `nRTCMinute` | 数值型 | 0 | 当前分钟 |
| `nRTCSecond` | 数值型 | 0 | 当前秒 |
| `nNowWeekMin` | 数值型 | 0 | 当前时间在一周内的分钟数 |
| `nMon1StartWeekMin` | 数值型 | 0 | 周一第1时段开始周分钟 |
| `nMon1EndWeekMin` | 数值型 | 0 | 周一第1时段结束周分钟 |
| `bMon1Active` | 数值型 | 0 | 当前是否处于该时段 |
| `nScheduleTarget` | 数值型 | 0 | 计算出的运行目标，0停机，1运行 |
| `nScheduleWriteRet` | 数值型 | 0 | `!SetDevice`调用返回信息，只用于诊断 |
| `nScheduleWriteCooldown` | 数值型 | 0 | 写入失败后的重试等待秒数 |
| `nScheduleClockError` | 数值型 | 0 | 0时间正常，1读取时间失败 |
| `nScheduleConfigError` | 数值型 | 0 | 0设置合法，1时间设置越界 |
| `nScheduleResult` | 数值型 | 0 | 定时脚本当前结果码 |
| `nScheduleExitStep` | 数值型 | 0 | 0正常，1停机后退出，2直接退出 |
| `nScheduleModeOne` | 数值型 | 0 | 写寄存器时使用的固定值1 |
| `nScheduleModeZero` | 数值型 | 0 | 写寄存器时使用的固定值0 |
| `strScheduleNow` | 字符型 | 空 | 画面显示的当前日期时间，长度32 |

### 4.5 第四步：建立“周定时”画面

#### 4.5.1 新建画面

1. 在工程左侧工作台找到`用户窗口`。
2. 在`用户窗口`上点鼠标右键，选择`新建窗口`。
3. 把新窗口改名为`周定时`。
4. 双击`周定时`，进入画面编辑状态。

#### 4.5.2 放置标题和静态文字

从工具箱选择`标签`，依次放置以下静态文字：

```text
周定时开关机
当前时间
星期一 第1时段
开始时间
结束时间
本地总使能
PLC控制方式
PLC定时目标
开关机步骤
故障停机状态
脚本结果码
```

这些标签只显示文字，不绑定变量。

#### 4.5.3 放置数据显示框

从工具箱选择`数据显示框`或`数值显示框`。如果当前版本没有这个名称，可以使用普通输入框并取消“允许输入”。

逐个建立以下只读显示：

| 显示内容 | 绑定变量 | 显示说明 |
|---|---|---|
| 当前日期时间 | `strScheduleNow` | 显示年月日、时分秒 |
| 本地总使能 | `bScheduleMasterEnable` | 0停用，1启用 |
| 本时段状态 | `bMon1Active` | 0不在时段，1正在时段内 |
| 当前计算目标 | `nScheduleTarget` | 0停机，1运行 |
| PLC控制方式 | `R0165_开关机控制方式` | 0普通，1定时 |
| PLC定时目标 | `R1388_定时运行目标` | 0停机，1运行 |
| 开关机步骤 | `R0709_开关机步骤` | 0停机，1启动，2运行，3/4/5停机 |
| 系统状态 | `R0700_系统状态` | PSC330当前状态 |
| 故障停机状态 | `R0710_故障停机状态` | 0无故障停机 |
| 脚本结果码 | `nScheduleResult` | 结果码见4.10 |
| 时间读取故障 | `nScheduleClockError` | 0正常，1故障 |
| 时间设置故障 | `nScheduleConfigError` | 0正常，1设置越界 |

绑定方法：

1. 双击刚放到画面上的显示框。
2. 在属性中找到`显示输出`、`表达式`或`连接变量`。
3. 点右侧的`?`或变量选择按钮。
4. 从实时数据库选择上表对应变量。
5. 对状态框关闭输入功能，防止操作员直接改诊断变量。

#### 4.5.4 放置4个时间输入框

从工具箱选择`输入框`或`数值输入框`，放置4个输入框：

| 输入框旁边的文字 | 绑定变量 | 最小值 | 最大值 | 小数位 |
|---|---|---:|---:|---:|
| 开始小时 | `nMon1StartHour` | 0 | 23 | 0 |
| 开始分钟 | `nMon1StartMin` | 0 | 59 | 0 |
| 结束小时 | `nMon1EndHour` | 0 | 23 | 0 |
| 结束分钟 | `nMon1EndMin` | 0 | 59 | 0 |

每个输入框的设置方法：

1. 双击输入框。
2. 在`操作属性`或`输入属性`中勾选允许输入。
3. 选择对应的本地变量。
4. 数据格式选整数，小数位设0。
5. 输入范围按上表设置。
6. 建议在画面上把小时和分钟排成`08 : 30`的样式，但小时和分钟仍是两个独立输入框。

#### 4.5.5 放置5个标准按钮

从工具箱选择`标准按钮`，依次建立：

```text
启用/停用本时段
启用周定时
退出定时并保持当前状态
停机并退出定时
返回
```

脚本不要放在`按下脚本`中。统一放在`抬起脚本`中，防止按住按钮或误触时重复执行。

设置脚本的通用步骤：

1. 双击标准按钮。
2. 打开按钮的`脚本程序`属性页。
3. 保持`按下脚本`为空。
4. 选择`抬起脚本`。
5. 点`打开脚本程序编辑器`。
6. 粘贴本章对应按钮的脚本。
7. 点检查或编译按钮，确认没有语法错误后保存。

“返回”按钮使用MCGS普通的打开窗口操作，返回原来的主画面，不需要参与定时算法。

### 4.6 第五步：加入1秒循环策略

#### 4.6.1 打开循环策略

1. 回到MCGSPro工作台。
2. 找到`运行策略`。
3. 双击`循环策略`。如果工程中已经有循环策略，使用现有循环策略，不要再建立多个互相写165和1388的策略。
4. 打开循环策略属性，把循环时间设置为`1000 ms`，即每1秒执行一次。
5. 在循环策略编辑区添加一个`脚本程序`构件。
6. 双击这个`脚本程序`构件，打开脚本程序编辑器。
7. 把下面4.6.2的完整脚本粘贴进去。

这个完整脚本只能放在`运行策略 -> 循环策略 -> 脚本程序`中，不能放在按钮脚本、窗口启动脚本或窗口循环脚本中。

#### 4.6.2 星期一第1时段完整循环脚本

```text
'========================================================
'周定时开关机：第一阶段，仅星期一第1时段
'放置位置：运行策略 -> 循环策略 -> 脚本程序
'执行周期：1000ms
'========================================================

'固定写入值，每次循环重新赋值，防止触摸屏重启后值未初始化
nScheduleModeOne = 1
nScheduleModeZero = 0

'--------------------------------------------------------
'1. 读取触摸屏当前时间
'--------------------------------------------------------
iScheduleNow = !TimeGetCurrentTime()

If iScheduleNow > 0 Then
    nRTCWeek = !TimeGetDayOfWeek(iScheduleNow)
    nRTCHour = !TimeGetHour(iScheduleNow)
    nRTCMinute = !TimeGetMinute(iScheduleNow)
    nRTCSecond = !TimeGetSecond(iScheduleNow)
    strScheduleNow = !TimeI2Str(iScheduleNow,"%Y-%m-%d %H:%M:%S")
    nScheduleClockError = 0
Else
    nScheduleClockError = 1
    nScheduleResult = 101
EndIf

'--------------------------------------------------------
'2. 检查时间设置范围
'--------------------------------------------------------
nScheduleConfigError = 0

If nMon1StartHour < 0 Or nMon1StartHour > 23 Then
    nScheduleConfigError = 1
EndIf
If nMon1StartMin < 0 Or nMon1StartMin > 59 Then
    nScheduleConfigError = 1
EndIf
If nMon1EndHour < 0 Or nMon1EndHour > 23 Then
    nScheduleConfigError = 1
EndIf
If nMon1EndMin < 0 Or nMon1EndMin > 59 Then
    nScheduleConfigError = 1
EndIf

If nScheduleConfigError = 1 Then
    nScheduleResult = 102
EndIf

'--------------------------------------------------------
'3. 计算星期一第1时段是否有效
'星期一索引为0；一周共10080分钟
'开始时间等于结束时间时，按“该时段禁用”处理
'--------------------------------------------------------
bMon1Active = 0

If nScheduleClockError = 0 Then
    If nScheduleConfigError = 0 Then
        nNowWeekMin = (nRTCWeek - 1) * 1440 + nRTCHour * 60 + nRTCMinute

        If bMon1Enable = 1 Then
            If nMon1StartHour <> nMon1EndHour Or nMon1StartMin <> nMon1EndMin Then
                nMon1StartWeekMin = 0 * 1440 + nMon1StartHour * 60 + nMon1StartMin
                nMon1EndWeekMin = 0 * 1440 + nMon1EndHour * 60 + nMon1EndMin

                '结束不晚于开始表示跨到星期二
                If nMon1EndWeekMin <= nMon1StartWeekMin Then
                    nMon1EndWeekMin = nMon1EndWeekMin + 1440
                EndIf

                If nNowWeekMin >= nMon1StartWeekMin Then
                    If nNowWeekMin < nMon1EndWeekMin Then
                        bMon1Active = 1
                    EndIf
                EndIf

                '该比较用于以后复制到星期日时段，处理星期日跨到下周一
                If nNowWeekMin + 10080 >= nMon1StartWeekMin Then
                    If nNowWeekMin + 10080 < nMon1EndWeekMin Then
                        bMon1Active = 1
                    EndIf
                EndIf
            EndIf
        EndIf

        nScheduleTarget = 0
        If bScheduleMasterEnable = 1 Then
            If bMon1Active = 1 Then
                nScheduleTarget = 1
            EndIf
        EndIf
    EndIf
EndIf

'--------------------------------------------------------
'4. 写入重试计时，每次循环为1秒
'--------------------------------------------------------
If nScheduleWriteCooldown > 0 Then
    nScheduleWriteCooldown = nScheduleWriteCooldown - 1
EndIf

'--------------------------------------------------------
'5. 停机并退出定时
'先把1388写0，等待709真正回到0，再把165写0
'--------------------------------------------------------
If nScheduleExitStep = 1 Then
    nScheduleTarget = 0

    If R1388_定时运行目标 <> 0 Then
        If nScheduleWriteCooldown = 0 Then
            !SetDevice(设备0,6,"WriteP(4,1388,WUB,1,nScheduleModeZero,nScheduleWriteRet)")
            nScheduleWriteCooldown = 5
            nScheduleResult = 7
        EndIf
    Else
        If R0709_开关机步骤 = 0 Then
            If R0165_开关机控制方式 <> 0 Then
                If nScheduleWriteCooldown = 0 Then
                    !SetDevice(设备0,6,"WriteP(4,165,WUB,1,nScheduleModeZero,nScheduleWriteRet)")
                    nScheduleWriteCooldown = 5
                    nScheduleResult = 8
                EndIf
            Else
                nScheduleExitStep = 0
                nScheduleResult = 5
            EndIf
        EndIf
    EndIf
Else
    '----------------------------------------------------
    '6. 直接退出定时，保持PSC330当前开关状态
    '只退出165，不主动改变1388
    '----------------------------------------------------
    If nScheduleExitStep = 2 Then
        If R0165_开关机控制方式 <> 0 Then
            If nScheduleWriteCooldown = 0 Then
                !SetDevice(设备0,6,"WriteP(4,165,WUB,1,nScheduleModeZero,nScheduleWriteRet)")
                nScheduleWriteCooldown = 5
                nScheduleResult = 9
            EndIf
        Else
            nScheduleExitStep = 0
            nScheduleResult = 6
        EndIf
    Else
        '------------------------------------------------
        '7. 正常周定时控制
        '时间读取或设置错误时不改变PLC当前目标
        '------------------------------------------------
        If bScheduleMasterEnable = 1 Then
            If nScheduleClockError = 0 Then
                If nScheduleConfigError = 0 Then
                    '确保165已经进入定时模式
                    If R0165_开关机控制方式 = 0 Then
                        If nScheduleWriteCooldown = 0 Then
                            !SetDevice(设备0,6,"WriteP(4,165,WUB,1,nScheduleModeOne,nScheduleWriteRet)")
                            nScheduleWriteCooldown = 5
                            nScheduleResult = 1
                        EndIf
                    Else
                        '165读回非0后，才允许写定时运行目标1388
                        If R1388_定时运行目标 <> nScheduleTarget Then
                            If nScheduleWriteCooldown = 0 Then
                                !SetDevice(设备0,6,"WriteP(4,1388,WUB,1,nScheduleTarget,nScheduleWriteRet)")
                                nScheduleWriteCooldown = 5
                                nScheduleResult = 3
                            EndIf
                        Else
                            nScheduleResult = 2
                        EndIf
                    EndIf
                EndIf
            EndIf
        EndIf
    EndIf
EndIf
```

粘贴后先点脚本编辑器中的`检查`、`语法检查`或`编译`。如果提示找不到`设备0`，说明项目中的设备名称不同；把脚本中全部`设备0`改成设备窗口显示的真实名称。

### 4.7 第六步：填写5个按钮的抬起脚本

#### 4.7.1 “启用/停用本时段”按钮

放置位置：`周定时`画面中该按钮的`抬起脚本`。

```text
If bMon1Enable = 0 Then
    bMon1Enable = 1
Else
    bMon1Enable = 0
EndIf
```

按一次从0变1，再按一次从1变0。旁边的`本时段状态`显示框显示的是当前是否正在计划时间内，不是这个使能设置；建议再增加一个只读框绑定`bMon1Enable`，标题写`本时段使能`。

#### 4.7.2 “启用周定时”按钮

放置位置：`周定时`画面中该按钮的`抬起脚本`。

```text
If nScheduleClockError <> 0 Then
    nScheduleResult = 101
Else
    If nScheduleConfigError <> 0 Then
        nScheduleResult = 102
    Else
        bScheduleMasterEnable = 1
        nScheduleExitStep = 0
        nScheduleWriteCooldown = 0
        nScheduleResult = 1
        nScheduleModeOne = 1
        !SetDevice(设备0,6,"WriteP(4,165,WUB,1,nScheduleModeOne,nScheduleWriteRet)")
    EndIf
EndIf
```

按下后不要只看`nScheduleWriteRet`。必须看`R0165_开关机控制方式`是否读回1。循环策略会在写入未生效时每5秒重试。

#### 4.7.3 “退出定时并保持当前状态”按钮

这个按钮只退出定时控制，不主动要求机组停机。例如机组当前正在运行，退出后由普通控制方式接管。PSC330选择“本地开关”时通常保持原开关状态；如果PSC330选择的是远程开关或PLC开关，退出定时后远程输入会立即接管，最终状态由远程输入决定。

放置位置：`周定时`画面中该按钮的`抬起脚本`。

```text
bScheduleMasterEnable = 0
nScheduleExitStep = 2
nScheduleWriteCooldown = 0
nScheduleResult = 9
nScheduleModeZero = 0
!SetDevice(设备0,6,"WriteP(4,165,WUB,1,nScheduleModeZero,nScheduleWriteRet)")
```

成功标志：`R0165_开关机控制方式`读回0，`nScheduleResult`最终变成6。

#### 4.7.4 “停机并退出定时”按钮

这个按钮先要求PSC330正常停机，等709回到0后再退出定时控制。不要在按钮脚本中直接同时写1388=0和165=0，否则PSC330可能还没有完成正常停机就失去定时控制来源。

放置位置：`周定时`画面中该按钮的`抬起脚本`。

```text
bScheduleMasterEnable = 0
nScheduleTarget = 0
nScheduleExitStep = 1
nScheduleWriteCooldown = 0
nScheduleResult = 7
nScheduleModeZero = 0
!SetDevice(设备0,6,"WriteP(4,1388,WUB,1,nScheduleModeZero,nScheduleWriteRet)")
```

成功过程：

1. `R1388_定时运行目标`先变为0。
2. `R0709_开关机步骤`进入正常停机步骤。
3. 设备全部按固件顺序停止后，709回到0。
4. 循环策略再把`R0165_开关机控制方式`写成0。
5. `nScheduleResult`最终变为5。

#### 4.7.5 “返回”按钮

1. 双击“返回”按钮。
2. 在按钮操作属性中选择`打开用户窗口`。
3. 目标窗口选择原来的主画面。
4. 这个按钮不填写定时脚本。

### 4.8 第七步：第一次运行前怎样设置

1. 先把工程保存并执行`下载工程`或启动MCGS运行环境。
2. 打开新建的`周定时`画面。
3. 核对`当前时间`是否与北京时间一致。日期、星期、小时或分钟不正确时，先校准触摸屏系统时间。
4. 确认`时间读取故障=0`、`时间设置故障=0`。
5. 确认`故障停机状态=0`。
6. 第一次测试前让机组完全停机，确认`开关机步骤=0`。
7. 设置星期一第1时段的开始和结束时间。
8. 按`启用/停用本时段`，使`bMon1Enable`显示1。
9. 按`启用周定时`。
10. 确认`PLC控制方式`由0变成1。只有读回1才表示真正进入定时模式。

如果测试当天不是星期一，不要等待到下周。先按4.11建立测试当天对应的一个时段，或者临时把循环脚本中的星期索引改成当天索引，测试完成后再改回正确值。

星期索引如下：

| 星期 | `!TimeGetDayOfWeek()`返回值 | 脚本星期索引 |
|---|---:|---:|
| 星期一 | 1 | 0 |
| 星期二 | 2 | 1 |
| 星期三 | 3 | 2 |
| 星期四 | 4 | 3 |
| 星期五 | 5 | 4 |
| 星期六 | 6 | 5 |
| 星期日 | 7 | 6 |

### 4.9 第八步：新手快速测试方法

假设当前时间是星期二14:20，准备测试星期二第1时段。如果已经按4.11建立了星期二变量，观察`bTue1Active`；如果只是把最小版脚本中的星期索引临时由0改成1，仍观察`bMon1Active`。

1. 把开始时间设置为14:22。
2. 把结束时间设置为14:25。
3. 启用该时段。
4. 确认709=0、710=0。
5. 按`启用周定时`。
6. 165必须读回1。
7. 14:22到达时，`bTue1Active`应变1，`nScheduleTarget`应变1，1388应读回1。
8. PSC330开始启动时，709应由0变1；完成开机后应变2。
9. 14:25到达时，Active和Target应变0，1388应读回0。
10. PSC330应执行正常停机流程，709最终回到0。

必须分别完成以下测试：

| 测试 | 设置方法 | 预期结果 |
|---|---|---|
| 普通时段 | 14:22至14:25 | 开始时启动，结束时正常停机 |
| 开始等于结束 | 14:22至14:22 | 该时段视为禁用，不应全天运行 |
| 跨午夜 | 23:58至00:03 | 当天23:58启动，次日00:03停机 |
| 两时段不重叠 | 08:00至10:00、14:00至18:00 | 两个时段分别运行 |
| 两时段重叠 | 08:00至12:00、10:00至14:00 | 08:00启动，重叠期间保持运行，14:00才停 |
| 启动中取消 | 709=1时把目标变0 | 应转入正常取消/停机，不得错误补开设备 |
| 故障禁止启动 | 710非0时到达开始时间 | 1388可为1，但PSC330保护逻辑不得强行启动 |
| 掉电保持 | 设置时段后重启触摸屏 | 时段使能和时间设置仍保留 |

启动中取消必须做实体复测。如果1388已经变0，但PSC330在709=1阶段反而补开送风机、回风机或其他设备，这是PSC330开关机状态机问题，不能把周定时判定为通过。

### 4.10 怎样判断成功、失败和结果码

不要以“按钮按下了”或`!SetDevice`函数执行过作为成功依据。最终必须看连接变量的读回值。

| 操作 | 成功判据 |
|---|---|
| 启用周定时 | 165读回1 |
| 定时开机命令成功 | 到时后1388读回1 |
| 实际开始启动 | 709由0变1 |
| 实际运行完成 | 709变2 |
| 定时停机命令成功 | 到时后1388读回0 |
| 实际停机完成 | 709最终回0 |
| 退出定时成功 | 165读回0 |

`nScheduleResult`含义：

| 值 | 含义 |
|---:|---|
| 0 | 尚未操作 |
| 1 | 正在写入定时控制方式 |
| 2 | 定时模式和当前运行目标已经一致 |
| 3 | 正在写入1388运行目标 |
| 5 | 已停机并退出定时 |
| 6 | 已退出定时，未主动改变当前开关状态 |
| 7 | 正在要求PSC330停机 |
| 8 | 已停机，正在退出定时方式 |
| 9 | 正在直接退出定时方式 |
| 101 | 触摸屏当前时间读取失败 |
| 102 | 开始或结束时间超出合法范围 |

常见问题：

| 现象 | 检查方法 |
|---|---|
| 165始终写不进去 | 检查`设备0`名称、串口通信和165连接变量地址 |
| 165已经为1，但1388不变化 | 检查循环策略是否运行、周期是否1000ms、时段是否启用 |
| 1388已经为1，但机组不启动 | 检查709是否为0、710是否有故障、消防和外部连锁是否允许 |
| 到时反复发送写命令 | 确认脚本只在读回值与目标不一致时写，并使用5秒重试计时 |
| 星期或时间不对 | 校准触摸屏系统时间；周定时以触摸屏时间为准 |
| 实际地址相差1 | 检查设备驱动使用0基还是1基；本项目当前脚本按0基地址编写 |
| 手动398在定时模式中不起作用 | 属于正常现象；先退出定时模式，再使用普通手动开关机 |

### 4.11 第九步：复制成每天两个时段

只有“单个时段快速测试”成功后才做这一步。

#### 4.11.1 创建全周设置变量

每个时段都要建立5个掉电保持数值变量：

```text
bMon1Enable nMon1StartHour nMon1StartMin nMon1EndHour nMon1EndMin
bMon2Enable nMon2StartHour nMon2StartMin nMon2EndHour nMon2EndMin
bTue1Enable nTue1StartHour nTue1StartMin nTue1EndHour nTue1EndMin
bTue2Enable nTue2StartHour nTue2StartMin nTue2EndHour nTue2EndMin
bWed1Enable nWed1StartHour nWed1StartMin nWed1EndHour nWed1EndMin
bWed2Enable nWed2StartHour nWed2StartMin nWed2EndHour nWed2EndMin
bThu1Enable nThu1StartHour nThu1StartMin nThu1EndHour nThu1EndMin
bThu2Enable nThu2StartHour nThu2StartMin nThu2EndHour nThu2EndMin
bFri1Enable nFri1StartHour nFri1StartMin nFri1EndHour nFri1EndMin
bFri2Enable nFri2StartHour nFri2StartMin nFri2EndHour nFri2EndMin
bSat1Enable nSat1StartHour nSat1StartMin nSat1EndHour nSat1EndMin
bSat2Enable nSat2StartHour nSat2StartMin nSat2EndHour nSat2EndMin
bSun1Enable nSun1StartHour nSun1StartMin nSun1EndHour nSun1EndMin
bSun2Enable nSun2StartHour nSun2StartMin nSun2EndHour nSun2EndMin
```

每个时段还要建立3个不保持的计算变量：

```text
nMon1StartWeekMin nMon1EndWeekMin bMon1Active
nMon2StartWeekMin nMon2EndWeekMin bMon2Active
nTue1StartWeekMin nTue1EndWeekMin bTue1Active
nTue2StartWeekMin nTue2EndWeekMin bTue2Active
nWed1StartWeekMin nWed1EndWeekMin bWed1Active
nWed2StartWeekMin nWed2EndWeekMin bWed2Active
nThu1StartWeekMin nThu1EndWeekMin bThu1Active
nThu2StartWeekMin nThu2EndWeekMin bThu2Active
nFri1StartWeekMin nFri1EndWeekMin bFri1Active
nFri2StartWeekMin nFri2EndWeekMin bFri2Active
nSat1StartWeekMin nSat1EndWeekMin bSat1Active
nSat2StartWeekMin nSat2EndWeekMin bSat2Active
nSun1StartWeekMin nSun1EndWeekMin bSun1Active
nSun2StartWeekMin nSun2EndWeekMin bSun2Active
```

#### 4.11.2 复制画面行

1. 在`周定时`画面框选“星期一第1时段”的启用按钮、4个时间输入框和状态显示。
2. 复制并粘贴13次。
3. 把标题依次改成星期一第2时段、星期二第1/2时段，直到星期日第2时段。
4. 双击每个输入框，把绑定变量改成对应日期、对应时段的变量。
5. 双击每个启用按钮，把按钮脚本中的`bMon1Enable`替换为该行的使能变量。
6. 双击每个状态显示，把绑定变量换成对应的`b...Active`变量。

#### 4.11.3 复制时段计算脚本

在4.6.2循环脚本的“3. 计算星期一第1时段是否有效”位置，把星期一第1时段计算块复制13份。每一份同时替换变量前缀和星期索引：

| 时段 | 变量前缀 | 星期索引 |
|---|---|---:|
| 星期一1 | `Mon1` | 0 |
| 星期一2 | `Mon2` | 0 |
| 星期二1 | `Tue1` | 1 |
| 星期二2 | `Tue2` | 1 |
| 星期三1 | `Wed1` | 2 |
| 星期三2 | `Wed2` | 2 |
| 星期四1 | `Thu1` | 3 |
| 星期四2 | `Thu2` | 3 |
| 星期五1 | `Fri1` | 4 |
| 星期五2 | `Fri2` | 4 |
| 星期六1 | `Sat1` | 5 |
| 星期六2 | `Sat2` | 5 |
| 星期日1 | `Sun1` | 6 |
| 星期日2 | `Sun2` | 6 |

还必须把“2. 检查时间设置范围”中的4条范围检查复制到每一个新增时段，并把变量名改成对应时段。例如星期二第1时段增加：

```text
If nTue1StartHour < 0 Or nTue1StartHour > 23 Then
    nScheduleConfigError = 1
EndIf
If nTue1StartMin < 0 Or nTue1StartMin > 59 Then
    nScheduleConfigError = 1
EndIf
If nTue1EndHour < 0 Or nTue1EndHour > 23 Then
    nScheduleConfigError = 1
EndIf
If nTue1EndMin < 0 Or nTue1EndMin > 59 Then
    nScheduleConfigError = 1
EndIf
```

14个时段一共应有56条小时/分钟范围检查。输入框虽然已经设置最小值和最大值，循环脚本仍要保留这些检查，以防掉电数据、工程导入或其他脚本写入了非法值。

例如复制成星期二第1时段时：

```text
bTue1Active = 0

If bTue1Enable = 1 Then
    If nTue1StartHour <> nTue1EndHour Or nTue1StartMin <> nTue1EndMin Then
        nTue1StartWeekMin = 1 * 1440 + nTue1StartHour * 60 + nTue1StartMin
        nTue1EndWeekMin = 1 * 1440 + nTue1EndHour * 60 + nTue1EndMin

        If nTue1EndWeekMin <= nTue1StartWeekMin Then
            nTue1EndWeekMin = nTue1EndWeekMin + 1440
        EndIf

        If nNowWeekMin >= nTue1StartWeekMin Then
            If nNowWeekMin < nTue1EndWeekMin Then
                bTue1Active = 1
            EndIf
        EndIf

        If nNowWeekMin + 10080 >= nTue1StartWeekMin Then
            If nNowWeekMin + 10080 < nTue1EndWeekMin Then
                bTue1Active = 1
            EndIf
        EndIf
    EndIf
EndIf
```

全部14个Active计算完成后，把原来只判断`bMon1Active`的目标合成部分替换为：

```text
nScheduleTarget = 0

If bScheduleMasterEnable = 1 Then
    If bMon1Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bMon2Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bTue1Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bTue2Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bWed1Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bWed2Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bThu1Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bThu2Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bFri1Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bFri2Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bSat1Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bSat2Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bSun1Active = 1 Then
        nScheduleTarget = 1
    EndIf
    If bSun2Active = 1 Then
        nScheduleTarget = 1
    EndIf
EndIf
```

最后重新执行脚本语法检查，并逐行核对：

1. 星期索引是否正确。
2. Enable、Start、End和Active变量是否属于同一行。
3. 每行的4个输入框是否绑定了正确变量。
4. 星期日跨午夜是否能够在星期一继续保持Active。
5. 任何两个时段重叠时，最终目标都应保持1，直到最后一个有效时段结束。

### 4.12 正式使用前的最终检查

1. MCGS循环策略周期必须是1000ms。
2. 工程中只能有一套脚本写165和1388。
3. 所有时间设置变量必须掉电保持。
4. 当前时间和计算变量不要掉电保持。
5. 定时按钮脚本只放在`抬起脚本`，不要同时放在按下和抬起。
6. 写入成功以165、1388读回为准，不以函数被调用为准。
7. 定时开机和停机最终以709的实际步骤为准。
8. 消防、外部连锁、风机故障等保护必须继续由PSC330执行，MCGS定时不得绕过保护。
9. 正式启用前必须实体测试普通时段、跨午夜、启动中取消、故障禁止启动和触摸屏掉电保持。

## 5. 校准通用规则

AI/NTC校准是单点偏移校准，不是量程斜率校准。计算公式：

```text
新偏移 = 原偏移 + 标准仪表值 - 当前设备显示值
```

计算必须使用寄存器内部单位：

- 温度：0.1摄氏度，25.0摄氏度对应250。
- 湿度：0.1%RH，50.0%RH对应500。
- 风速：0.1m/s，3.2m/s对应32。
- 压差、压力、CO2按当前显示寄存器的整数工程单位。
- 若PSC316压力页面使用MPa输入，必须先乘1000换算为kPa整数。

通用禁止条件：

- 当前值为9999或传感器故障时禁止校准。
- 标准仪表尚未稳定时禁止校准。
- 新偏移超过允许范围时禁止写入。
- 同一传感器连续校准时，每次必须使用最新读回的原偏移。

## 6. PSC330 AI/NTC校准

### 6.1 AI地址

| 通道 | 功能 | 当前值地址 | 偏移地址 | 当前值内部单位 | 偏移范围 |
|---:|---|---:|---:|---|---:|
| AI0 | 房间压差 | 500 | 499 | Pa | -5000..5000 |
| AI1 | 回风/房间湿度 | 501 | 498 | 0.1%RH | -5000..5000 |
| AI2 | CO2 | 903 | 497 | ppm | -5000..5000 |
| AI3 | 送风压力 | 1125 | 496 | Pa | -5000..5000 |
| AI3 | 送风风速 | 1126 | 496 | 0.1m/s | -5000..5000 |
| AI4 | 新风湿度 | 519 | 457 | 0.1%RH | -5000..5000 |

参数308为1时AI3按风压使用；其他值按风速/风量路径使用。AI3压力和风速共用同一个偏移地址496，必须按当前实际控制用途校准，不能分别保存两套偏移。

AI0至AI4输入类型地址为459至463，当前默认0至10V。参数432同时约束AI1/AI4湿度输入：0为0至10V，1为4至20mA。校准前先确认接线类型和量程设置正确；错误的输入类型不能靠偏移修正。

### 6.2 NTC地址

| 通道 | 功能 | 当前值地址 | 偏移地址 |
|---:|---|---:|---:|
| NTC0 | 回风/房间温度 | 511 | 495 |
| NTC1 | 送风温度 | 510 | 494 |
| NTC2 | 新风温度 | 512 | 493 |
| NTC3 | 预热后温度 | 513 | 492 |
| NTC4 | A-1蒸发盘管 | 515 | 491 |
| NTC5 | A-2蒸发盘管 | 516 | 490 |
| NTC6 | B-1蒸发盘管 | 514 | 489 |
| NTC7 | B-2蒸发盘管 | 517 | 488 |
| NTC8 | C-1蒸发盘管 | 520 | 487 |
| NTC9 | C-2蒸发盘管 | 521 | 486 |
| NTC10 | D-1蒸发盘管 | 522 | 485 |
| NTC11 | D-2蒸发盘管 | 523 | 484 |

NTC偏移范围为-500至500，即-50.0至+50.0摄氏度。

### 6.3 计算示例

NTC0当前显示24.3摄氏度，标准温度25.0摄氏度，原偏移-0.2摄氏度：

```text
当前值寄存器 = 243
标准值内部值 = 250
原偏移寄存器 = -2
新偏移 = -2 + 250 - 243 = 5
```

应向495写入5，表示+0.5摄氏度。

### 6.4 MCGS本地变量

| 变量 | 类型 | 用途 |
|---|---|---|
| `n330CalChannel` | 整数 | 当前校准通道 |
| `d330CalReference` | 浮点 | 用户输入标准工程值 |
| `n330CalReferenceRaw` | 整数 | 换算后的寄存器内部值 |
| `n330CalExpectedOffset` | 整数 | 预计写入偏移 |
| `n330CalWriteRet` | 整数 | 写命令返回诊断 |
| `n330CalCheck` | 整数 | 写后监视使能 |
| `n330CalTimeout` | 整数 | 200ms计数 |
| `n330CalSaveWait` | 整数 | 读回成功后的保存等待计数 |
| `n330CalResult` | 整数 | 结果码 |

建议结果码：

- 0空闲
- 1写入中
- 2寄存器读回成功
- 3已等待5秒，可以进行断电验证
- 101当前值无效
- 102偏移超范围
- 103写入读回超时

### 6.5 固定地址写入模板

以NTC0为例，标准输入单位为摄氏度：

```text
n330CalReferenceRaw = d330CalReference * 10

If R0511_NTC0回风温度 = 9999 Then
    n330CalResult = 101
    Exit
EndIf

n330CalExpectedOffset = R0495_NTC0偏移 + n330CalReferenceRaw - R0511_NTC0回风温度

If n330CalExpectedOffset < -500 Or n330CalExpectedOffset > 500 Then
    n330CalResult = 102
    Exit
EndIf

n330CalResult = 1
n330CalCheck = 1
n330CalTimeout = 0
n330CalSaveWait = 0
!SetDevice(设备0,6,"WriteP(4,495,WB,1,n330CalExpectedOffset,n330CalWriteRet)")
```

以AI0房间压差为例，标准输入单位为Pa，不乘10：

```text
n330CalReferenceRaw = d330CalReference
n330CalExpectedOffset = R0499_AI0偏移 + n330CalReferenceRaw - R0500_AI0房间压差

If n330CalExpectedOffset < -5000 Or n330CalExpectedOffset > 5000 Then
    n330CalResult = 102
    Exit
EndIf

n330CalResult = 1
n330CalCheck = 1
n330CalTimeout = 0
n330CalSaveWait = 0
!SetDevice(设备0,6,"WriteP(4,499,WB,1,n330CalExpectedOffset,n330CalWriteRet)")
```

每个通道按钮应使用表中的固定地址。不要通过字符串拼接动态生成`WriteP`地址。

### 6.6 读回和保存等待

200ms周期，以NTC0为例：

```text
If n330CalCheck <> 1 Then
    Exit
EndIf

n330CalTimeout = n330CalTimeout + 1

If R0495_NTC0偏移 = n330CalExpectedOffset Then
    n330CalResult = 2
    n330CalCheck = 0
    n330CalSaveWait = 1
    Exit
EndIf

If n330CalTimeout >= 50 Then
    n330CalResult = 103
    n330CalCheck = 0
EndIf
```

另设200ms周期保存等待：

```text
If n330CalSaveWait > 0 Then
    n330CalSaveWait = n330CalSaveWait + 1

    '25次乘200ms等于5秒
    If n330CalSaveWait >= 25 Then
        n330CalSaveWait = 0
        n330CalResult = 3
    EndIf
EndIf
```

PSC330校准参数变化稳定约500ms后才开始写EEPROM，固件使用双槽、CRC、提交标记和写后校验。MCGS等待5秒是保守的操作窗口，但最终仍必须真实断电重启验证；ST-Link复位不能替代断电验证。

## 7. PSC316 AI/NTC校准

PSC316必须逐台写入。禁止把同一校准值广播到1至4号外机。

### 7.1 网关诊断地址

| 外机 | 在线 | 写状态 | 错误码 |
|---:|---:|---:|---:|
| 1 | 1872 | 1873 | 1874 |
| 2 | 1920 | 1921 | 1922 |
| 3 | 1968 | 1969 | 1970 |
| 4 | 2016 | 2017 | 2018 |

写状态：

- 0：空闲
- 1：网关正在写入或读回
- 2：PSC316目标寄存器读回与写入值一致
- 3：失败

错误码：

- 1：超范围
- 2：通信失败
- 3：网关忙
- 4：读回不一致
- 5：外机地址不一致
- 6：运行中禁止写入
- 7：规格组合非法
- 8：必须成组写入

校准写入通常是单寄存器，但操作时仍建议330和目标316停机。状态2只证明PSC316寄存器读回成功，不证明EEPROM已经经受断电。

### 7.2 压力AI校准地址

PSC316目标含义：

| AI | 功能 | PSC316内部参数 |
|---:|---|---:|
| AI0 | 压缩机1高压 | 499 |
| AI1 | 压缩机2高压 | 498 |
| AI2 | 压缩机1低压 | 497 |
| AI3 | 压缩机2低压 | 496 |

通过PSC330写入的固定地址：

| 外机 | AI0 | AI1 | AI2 | AI3 |
|---:|---:|---:|---:|---:|
| 1 | 2654 | 2655 | 2656 | 2657 |
| 2 | 2658 | 2659 | 2660 | 2661 |
| 3 | 2662 | 2663 | 2664 | 2665 |
| 4 | 2666 | 2667 | 2668 | 2669 |

范围为-5000至5000，使用`WB`。

实时压力地址以每台70字为一组：

```text
1号外机基址1550
2号外机基址1620
3号外机基址1690
4号外机基址1760

压缩机1高压 = 基址 + 23
压缩机1低压 = 基址 + 24
压缩机2高压 = 基址 + 25
压缩机2低压 = 基址 + 26
```

注意实时显示顺序是高压1、低压1、高压2、低压2；校准网关顺序是高压1、高压2、低压1、低压2。画面绑定时不要按顺序直接复制。

### 7.3 NTC校准地址

| 通道 | 功能 |
|---:|---|
| NTC0 | 室外环境温度 |
| NTC1 | 盘管1温度 |
| NTC2 | 盘管2温度 |
| NTC3 | 排气1温度 |
| NTC4 | 排气2温度 |
| NTC5 | 吸气1温度 |
| NTC6 | 吸气2温度 |
| NTC7 | 阀后温度1 |

通过PSC330网关的固定地址：

| 外机 | NTC0至NTC7地址 |
|---:|---|
| 1 | 2534至2541 |
| 2 | 2550至2557 |
| 3 | 2566至2573 |
| 4 | 2582至2589 |

这些地址分别映射PSC316参数1506至1513。范围为-500至500，内部单位0.1摄氏度，使用`WB`。

实时温度地址：

```text
每台外机基址仍为1550、1620、1690、1760

环境温度   = 基址 + 2
阀后温度1  = 基址 + 3
盘管1温度  = 基址 + 11
盘管2温度  = 基址 + 12
排气1温度  = 基址 + 13
排气2温度  = 基址 + 14
吸气1温度  = 基址 + 15
吸气2温度  = 基址 + 16
```

当前硬件没有阀后温度2物理NTC，该点显示9999，不得放入校准页面。

### 7.4 写入脚本示例

以1号外机NTC0为例：

```text
If R1872_1号外机在线 <> 1 Then
    n316CalResult = 107
    Exit
EndIf

If R1552_1号外机环境温度 = 9999 Then
    n316CalResult = 101
    Exit
EndIf

n316CalReferenceRaw = d316CalReference * 10
n316CalExpectedOffset = R2534_1号外机NTC0偏移 + n316CalReferenceRaw - R1552_1号外机环境温度

If n316CalExpectedOffset < -500 Or n316CalExpectedOffset > 500 Then
    n316CalResult = 102
    Exit
EndIf

n316CalResult = 1
n316CalCheck = 1
n316CalTimeout = 0
n316CalSawBusy = 0
n316CalSaveWait = 0
!SetDevice(设备0,6,"WriteP(4,2534,WB,1,n316CalExpectedOffset,n316CalWriteRet)")
```

以1号外机AI0高压为例。若页面标准值使用kPa，则不缩放；若使用MPa，需要乘1000：

```text
n316CalReferenceRaw = d316CalReference
n316CalExpectedOffset = R2654_1号外机AI0偏移 + n316CalReferenceRaw - R1573_1号外机高压1

If n316CalExpectedOffset < -5000 Or n316CalExpectedOffset > 5000 Then
    n316CalResult = 102
    Exit
EndIf

n316CalResult = 1
n316CalCheck = 1
n316CalTimeout = 0
n316CalSawBusy = 0
n316CalSaveWait = 0
!SetDevice(设备0,6,"WriteP(4,2654,WB,1,n316CalExpectedOffset,n316CalWriteRet)")
```

其他外机和通道必须替换成表中的固定地址。最稳妥的画面是每台外机一个页签，每行一个固定写按钮。

### 7.5 网关结果监视

以1号外机NTC0为例，200ms周期：

```text
If n316CalCheck <> 1 Then
    Exit
EndIf

n316CalTimeout = n316CalTimeout + 1

If R1873_1号外机写状态 = 1 Then
    n316CalSawBusy = 1
EndIf

If R1873_1号外机写状态 = 2 Then
    If n316CalSawBusy = 1 Then
        If R2534_1号外机NTC0偏移 = n316CalExpectedOffset Then
            n316CalResult = 2
            n316CalCheck = 0
            n316CalSaveWait = 1
            Exit
        Else
            n316CalResult = 104
            n316CalCheck = 0
            Exit
        EndIf
    EndIf
EndIf

If R1873_1号外机写状态 = 3 Then
    If n316CalSawBusy = 1 Then
        n316CalResult = 103
        n316GatewayError = R1874_1号外机错误码
        n316CalCheck = 0
        Exit
    EndIf
EndIf

'20秒超时
If n316CalTimeout >= 100 Then
    n316CalResult = 105
    n316GatewayError = R1874_1号外机错误码
    n316CalCheck = 0
EndIf
```

必须观察到状态1后，才接受本次状态2或3，避免把上一次残留的完成状态误认为本次结果。

读回成功后，同样等待至少5秒：

```text
If n316CalSaveWait > 0 Then
    n316CalSaveWait = n316CalSaveWait + 1

    If n316CalSaveWait >= 25 Then
        n316CalSaveWait = 0
        n316CalResult = 3
    EndIf
EndIf
```

## 8. 验收流程

### 8.1 维护提醒

1. 将362设为1，363临时设为1小时。
2. 确认停机时373不增加。
3. 正常运行累计达到1小时，确认894变1并显示提醒。
4. 点“稍后提醒”，确认只隐藏窗口，894仍为1。
5. 点“保养完成”，确认364自动回0、373回0、894回0。
6. 断电重启，确认维护设置和累计值符合设计要求。

### 8.2 周定时

至少测试：

- 同一天普通时段，例如08:00至10:00。
- 两个时段相邻、分离和重叠。
- 跨午夜，例如星期一23:00至星期二02:00。
- 星期日23:00至星期一02:00的跨周情况。
- 开始时间等于结束时间，确认该时段禁用。
- 运行中到停机时刻，确认执行正常停机顺序。
- 停机中再次到启动时刻，确认709未回0前不强行重启。
- 故障、消防、外部连锁存在时，确认定时命令不能绕过保护。
- 退出定时保持当前状态。
- 停机并退出定时，确认709回0后165才写0。
- 触摸屏和控制器同时断电重启，确认周计划设置仍保留。

### 8.3 PSC330校准

每类至少测试一个正偏移、一个负偏移、零偏移和上下边界：

1. 记录当前值和原偏移。
2. 输入标准仪表值。
3. 核对MCGS计算的新偏移。
4. 写入并确认偏移寄存器读回一致。
5. 等待5秒后记录工程值变化。
6. 真实断电，等待设备完全失电后重新上电。
7. 核对偏移和工程值仍正确。
8. 连续断电重启3次，检查丢失、串位或恢复默认。

PSC330重点覆盖AI偏移499至496、457，以及NTC偏移495至484。

### 8.4 PSC316校准

1. 分别选择1至4号外机。
2. 每台写入不同的小偏移，例如1、2、3、4，禁止使用相同值代替独立性测试。
3. 确认只有目标外机网关状态进入1，随后进入2。
4. 确认目标偏移读回一致，其他三台不变化。
5. 等待至少5秒。
6. 对目标PSC316真正断电重启，不能只复位330。
7. 确认目标PSC316偏移仍保留。
8. 依次完成4台独立保存验证。
9. 拔掉一台PSC316通信，确认只报告该台错误2，不误写其他外机。

现场不足4台板卡时，只能记录“已验证在线板卡”，不能把四台独立性标记为通过。

## 9. 关键结论

- 维护时间累计由PSC330完成，MCGS不应重复累计运行小时。
- 周定时由MCGS RTC计算，PSC330只接收1388最终启停目标。
- 1388必须仅在目标变化时写入，不能每秒重复写。
- AI/NTC偏移允许负数，必须使用`WB`。
- PSC330校准可直接写固定寄存器。
- PSC316校准必须通过对应外机的固定网关地址逐台写入。
- 网关状态2和寄存器读回一致仍不等于EEPROM断电保存成功。
- 任何保存功能最终都要经过真实断电重启验证。
