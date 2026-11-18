# 代码和接口定位

相对项目根定位；行号会漂移，优先按函数名搜索。

|范围|入口|
|---|---|
|316设定默认、范围、扫描顺序|PSC316RK-V12-外机/WELLTHINKER/User/user.c：ParameterInit、User|
|316地址宏与最终IO映射|同目录User.h：OUTDOOR_SPEC、PLCREADPara、HandD、末次#undef/#define|
|环境许可、禁用、风机、最终钳制|UserAction.c：AmbientProtectAction、OutdoorUnitAction、OutdoorFanPrestart、OutdoorFanTypeI/II/III、OutdoorHeatFanStageUpdate、OutdoorProtectOutputLimit|
|压机实际运行计时和四通阀|moduleAction.c：ModuleCompCount、ModuleCompAction|
|化霜|DefAction.c：DefEnable、PSC316DefrostUnavailable、PSC316DefrostGrant、PSC316DefrostAction、PSC316PublishDefrostState、DefrostProcess|
|保护和输出|ErrorCheck.c：SensorErrAction、CompErrAction、ErrorProcess、ErrorReset、IoOutAction|
|温度/压力换算|TempFilter.c、UserAction.c：OutdoorPTTempFromPressure、OutdoorCondTemps、OutdoorRunningSystemMask|
|正式/BENCH时间|两项目各自control_timing.h；确认宏是否编入实际AXF|
|330网关/共享参数/化霜仲裁|PSC330RK-V10-内机/User/UserSrc/modulecontrol.c：PSC316Gateway_SharedValue、PSC316SharedMirrorFromUnit1、PSC316UpdateDefrostOwner|
|330压机候选/禁用|同目录CompAction.C及相关调用，按CompIsConfigured、DeviceStatusCount等符号查找|

316实际输出为Y00/Y01压机，Y02风机1/低速/VFD运行，Y03风机2/定频，Y04/Y05四通阀，Y06底盘加热，Y07双速高速。旧宏名中的Y03/Y04/Y05不等于当前物理点；一定读User.h末次映射。

316 1420/1421化霜生命周期：0无，1请求，5手动请求，6不可参与，8正在化霜，7共同恢复。330镜像1550+(台−1)*70；330保护分层2598+(台−1)，逐条故障2022+(台−1)*128，锁存历史2618+(台−1)。版本2628+(台−1)*6，单位运行秒2670+(台−1)*2。

316四通阀[193]当前被共享[41]覆盖；当前实现并非规格授权，网关写后回读必须验证持续有效。共享LWS/RWS/TL/TLD/Z/ZD可能来自330共享区并周期广播，不能只改316单点然后误判控制器不响应。

离线可复用tools/test_defrost_lifecycle_arm.py的Firmware执行器，但其默认路径可能指向旧构建。新审阅显式传入已核实包内AXF，并核对源码清单。tools/audit_outdoor_spec_20261109.py是本次固定版本观察脚本；退出0仅表示记录写出，需看每条PASS/FAIL及证据范围。

user.c包含历史混合编码注释，不能直接按UTF8整文件重写。必要时仅诊断副本用转义显示坏字节，固件原字节保留。
