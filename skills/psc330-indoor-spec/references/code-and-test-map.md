# 项目入口和证据定位

仓库根目录由当前工作区确定，勿假设固定盘符。330位于PSC330RK-V10-内机，316位于PSC316RK-V12-外机；两者与根目录可各有独立Git状态。先读相关AGENTS，保留当前未提交内容。

| 条款 | 330入口（User/UserSrc，名称可rg搜索） | 对照重点 |
|---|---|---|
|3.1|UserAction.c / IndoorFanValveOutputs、IndoorValidateAoConfig、IndoorApplyHeatAnalogOutputs|模式许可、独立/共用、AO通道互斥、DO运行使能|
|3.2|UserAction.c、EEPROM保存及sysrun对象路径|开机意图/模式/温度保存，复位与断电分开|
|3.3|SysBoardAction、SysDataPross、IndoorModeTransitionAction、IndoorDisinfectExhaustAction|等待起点和完成反馈；紧停EEV+10|
|3.4|NergryAdjust.c / SysNergryAction_PID；CompAction.c；ErrorCheck.c|PID/YS/BX、ceil/floor/Z0、时长排序、盘管逐回路|
|3.5|UserAction.c / IndoorAutoCoolHeatSwitchAction|环境模式禁用、QHS重置、旧模式完整停完|
|3.6/3.7/3.8|IndoorPidDemandStep、HeatControl_UP、PreHeatControl、HumidtCtrl|符号、单位、历史样本、死区、余量、故障优先级|
|3.9|EEV_ActionAll、EEV_Priority及EEV源文件|制冷内阀、制热外阀、化霜内350、关闭20步/秒|
|3.10|FanControl.c / FanAction；最终输出约束及IoOutAction|自动反馈、手动回风、DA7/Y03和DA4/Y06|
|3.11|ErrorCheck.c / BoardErrAction；IndoorPressureReady|DI过滤、锁存/恢复、AI3停负载范围、介质防冻|

地址仅作检索线索，读当前User.h和协议后使用：模式1/236；总状态700/709；329送风1DO/2手动AO/3自动AO，330回风0无/1DO/2手动AO，331排风0无/1DO；供风DA7+Y03、回风DA4+Y06，Y10为排风；128制热方式、332再热、333预热、334加湿，枚举偏移不同，勿直接复制数值。

## 校准与输出单位

- NTC0偏移495，后续按通道递减；合法偏移±10℃。AI0～4的新偏移1237/1249/1261/1273/1285，配置基址1229、每路12字。旧499/498/497/496/457已弃用，不作为新AI偏移；495不能再作为AI4播种源。
- 大多数温湿度工程量0.1单位，PID能力0～1000。风机手动电压参数0～100对应0～10V，DA数组0～1000。不能把需求400误称为某路AO4V；SCR余量需要另算。
- DO数组Y00..Y07后接Y10..Y17，Y10是数组索引8，不是索引10。
- 现有默认参数、配置持久化、支持范围必须从当前构建核对；校准写入后回读，不用越界校准伪造不可达温度。AI物理信号注入和工程量映射注入分别标记。

## 证据目录

项目按日期报告及.codex-tmp/<批次>/JSON保存检查、原值、回读、异常、恢复和AXF哈希。2026-11-04的室内3.1_3.2_3.3、室内3.4-3.8、台面测试结果及调试记录都需交叉读取，不能只看单页汇总。最新逐条总表和明日计划是项目文档，不作为永久规格。

BENCH允许在动力断开控制板台架加速。正式时序按原文；软件固定计数、可配置参数、实际动作反馈各自记录。端子测量应记仪表、电气连接、时刻和误差，不能用两个同源寄存器冒充双重证据。
