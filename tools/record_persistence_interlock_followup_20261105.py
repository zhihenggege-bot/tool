"""Record current evidence without deleting the earlier failures."""
import json
from pathlib import Path
from run_indoor_bench_20261105 import D, R, RESULTS, result, now


def main():
    sensor = D / 'sensor_precondition_133004.json'
    diagnostic = json.loads(sensor.read_text('utf-8'))
    assert len(diagnostic['samples']) >= 15
    assert all(s['raw_ai'][1] == 9999 and s['SensorStatus'][1] == 1
               for s in diagnostic['samples'])
    audit = D / 'independent_audit_133117.json'
    a = json.loads(audit.read_text('utf-8'))
    assert not a.get('audit_error') and not a['after_reset_differences_from_preflight']
    persistence = D / 'persistence_fixed_125804.json'
    p = json.loads(persistence.read_text('utf-8'))
    assert p['passed'] and p['observed_race_trials'] == 20
    result('T03-001', '环境受限',
           'V10.49加湿联锁复测未到故障注入：AI1原始9999、SensorStatus[1]=1持续12秒以上；触发的是330[619]室内湿度故障，非[618]室温。此前两次复测前置失败保留，不能判联锁失败或通过',
           sensor, '本轮已停机恢复参数，并通过独立ST-Link复位终检；待恢复AI1有效信号后重跑X06/X07×冷/热×AO/DO八例',
           '只读Modbus及SWD；未屏蔽底层故障，未强写RAM输出')
    for cid, address, limits in [('T07-062',340,'默认10V、保留现有0～10V范围'),
                                 ('T07-065',345,'默认5Pa、保留现有0～9999Pa范围')]:
        result(cid, '按用户要求保留', f'用户2026-11-05明确不处理[{address}]范围；{limits}。原范围差异仍保留在历史，不计入待修复缺陷',
               R / '.codex-tmp/persistence_interlock_v1049_v1239_20261105/change_manifest.json',
               '本次没有修改该参数默认值、范围或行为；此状态不代表严格符合原文范围')
    result('T02-013', '部分通过',
           'V10.49保存竞态专项实板复测：20次命中EEPROM校验窗口，134改0后参数与DA7持续保持0并最终保存；普通参数与AI交错写入后复位回读一致。旧版可复现回滚；历史首次0V异常缺少轨迹，不能断言同因',
           persistence, '本轮参数已恢复并独立复位确认；物理0V端子、正式版实板及真实掉电未测')

    data = json.loads(RESULTS.read_text('utf-8'))
    counts = {s: sum(v['status'] == s for v in data.values()) for s in sorted({v['status'] for v in data.values()})}
    header = f'''# 内机测试版阶段结论（2026-11-05）

更新时间：{now()}。以下是当前结论；文末保留V10.48历史阶段，不能把旧失败直接当成新版本复测结果。

当前三板为330 V10.49、两块316 V12.39 **测试版**，均已烧录、逐字节校验。正式版同源修复且已编译，尚未烧录或完成正式秒数实测。[烧录证据](测试证据/内机实测_20261105/BENCH_V1049_V1239/flash.json)。

|事项|当前结果|剩余边界|
|---|---|---|
|[340]、[345]范围|按用户要求保留，未修改|原文范围差异记录保留，不列待修缺陷|
|330/316普通参数保存竞态、330 AI保存中新值确认|已修复，两档构建0错误0警告；659项针对性ARM检查通过|316保存竞态目前为离线验证，不能称已做两块316硬件保存矩阵|
|330连续改参、0V专项|旧版板上复现回滚；修复后20次命中竞态窗口，0V参数和软件DA7保持并保存；普通/AI交错保存、复位读回一致|原最早一次0V异常仍缺充分轨迹，不能直接归为同因；未测物理端子|
|制冷电热故障→加湿AO/DO关闭|V10.49已修代码，正式/测试两档ARM检查通过|实板复测前置被AI1故障中断，尚未验证修复通过；X06/X07×冷/热×AO/DO八例待有效输入重跑|
|AI1前置异常|12秒持续读到AI1=9999、SensorStatus[1]=1；室温及NTC0有效|根因暂定为底层AI输入无效，未判定具体接线/信号源损坏；量程调整未消除故障，不屏蔽故障凑通过|
|停止、恢复、独立复位终检|普通参数0～499、新AI1229～1288、档位1298/1299与烧前一致；复位后30.1秒三板通信正常、内机故障全0、负载输出全0|Y05报警输出按台架外机未配压力探头单列，不冒充所有DO全0；真实掉电未测|

目前逐项表共{len(data)}条：{counts}。这是跨版本证据集合，不是V10.49完整验收结果。原“87项部分通过”不能因本次修复自动转为通过，主要仍缺HMI、物理端子和正式时序证据。

证据：[保存竞态专项](测试证据/内机实测_20261105/BENCH_V1049_V1239/persistence_fixed_125804.json)、[传感器只读诊断](测试证据/内机实测_20261105/BENCH_V1049_V1239/sensor_precondition_133004.json)、[恢复及复位终检](测试证据/内机实测_20261105/BENCH_V1049_V1239/independent_audit_133117.json)、[双档产物与检查](.codex-tmp/persistence_interlock_v1049_v1239_20261105/)。

纠正续接时的故障定位：原始数组非零索引25，对应594+25=619；在330为ROOMHumidtyErr/SensorErr[1]。此前“618室温”及套用316表称“阀后”均不成立。完整原始JSON保留。等端点映射不是本次底层故障已证实的原因。

接下来先恢复AI1有效物理信号，再跑八例加湿联锁；物理AO/DO、真实断电和正式时序仍按原方案逐项补测。

<!-- HISTORY_V1048_START -->
## V10.48历史阶段记录（保留）

'''
    stage = R / '内机测试版阶段结论_20261105.md'
    old = stage.read_text('utf-8')
    if '<!-- HISTORY_V1048_START -->' in old:
        old = old.split('<!-- HISTORY_V1048_START -->',1)[1].split('## V10.48历史阶段记录（保留）',1)[1].lstrip()
    stage.write_text(header + old, encoding='utf-8')
    log = R / '调试记录_电工房直膨机组_20261015.md'
    with log.open('a', encoding='utf-8') as f:
        f.write(f'''\n\n## 2026-11-05 V10.49/V12.39 保存竞态及加湿联锁修复续测\n\n
两板普通参数保存改为写入快照并确认该快照，不用后续新值误判旧写入失败；330 AI保存确认保留期间新值的dirty状态，普通保存与AI保存互斥；330电热故障联锁覆盖制冷加湿AO/DO。用户明确不改[340]/[345]。正式/测试双档已构建，0错误0警告；130保存联锁+259启停+162风机+108时序=659项ARM检查通过。三块板已烧测试版并逐字节校验，正式版未烧。\n\n
330实板20次命中保存竞态窗口，0V参数与软件DA7不回滚且最终保存；普通参数/AI交错写入复位回读一致。原最早0V异常不直接归同因。加湿联锁本轮实板尚未获得有效结论，前置被AI1原始9999/底层故障中断。故障索引25是330[619]湿度，不是618室温，更不是套316地址表的阀后温度；前次错误定位已纠正。量程改为非零跨度后仍故障，不能归因于等端点。\n\n
已正常停机、恢复参数、独立ST-Link复位终检：0～499/1229～1288/1298～1299与烧前快照一致；复位后30.1秒版本/通信正常、内机故障0、负载AO/DO全0。Y05台架外机压力故障单列。用户需恢复AI1有效信号后重跑X06/X07×冷/热×AO/DO八例；不屏蔽底层保护。物理端子/真实断电/正式秒数未测。证据目录`测试证据/内机实测_20261105/BENCH_V1049_V1239/`；详见《内机测试版阶段结论_20261105.md》。时间{now()}。\n''')
    for file in (stage, R/'内机测试版逐项测试记录_20261105.md', log):
        assert '\ufffd' not in file.read_text('utf-8'), file
    print('REPORTS UPDATED', counts)


if __name__ == '__main__':
    main()
