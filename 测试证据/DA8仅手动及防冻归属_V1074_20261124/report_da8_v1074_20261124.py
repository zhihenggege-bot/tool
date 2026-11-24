"""Finalize DA8 evidence only after both board passes and baseline audit."""
import json
import shutil
from pathlib import Path
import deploy_da8_manual_v1074_20261124 as dep


def main():
    day=dep.DAY
    audit=json.loads((day/'final_audit.json').read_text('utf8'))
    deployment=json.loads((day/'deployment.json').read_text('utf8'))
    main_test=json.loads((day/'board_manual.json').read_text('utf8'))
    electric=json.loads((day/'board_electric_separation.json').read_text('utf8'))
    assert all(q['passed'] for q in (audit,deployment,main_test,electric))
    scoped=day/'scope_and_artifacts.json'
    scope=json.loads(scoped.read_text('utf8'))
    scope.update(flashed=True,hardware_tested=True,
        board_cases=len(main_test['cases'])+len(electric['cases']),
        final_baseline_restored=True,physical_terminal_measured=False,
        final_audit='final_audit.json')
    dep.dump(scoped,scope)
    traces={}
    for filename in ('board_samples.jsonl','board_manual_samples.jsonl','board_electric_separation_samples.jsonl'):
        path=day/filename
        if not path.exists():continue
        rows=[json.loads(line) for line in path.read_text('utf8').splitlines()]
        traces[filename]=dict(samples=len(rows),started=rows[0]['at'],finished=rows[-1]['at'],
            sha256=dep.d.sha(path),unexpected_outdoor_compressor_gpio_samples=sum(
                any(v for board in z['outdoor'] for v in board['gpio'][:2]) for z in rows))
        assert not traces[filename]['unexpected_outdoor_compressor_gpio_samples']
    dep.dump(day/'trace_inventory.json',traces)
    report=day/'修改与验证说明.md'
    text=report.read_text('utf8')
    old='尚未烧录和上板复测，也未测量实体端子电压或水阀实际行程。硬件当前程序不能据此视为已升级。'
    assert old in text
    text=text.replace(old,
        f"已于2026-11-24烧录330 V10.74正式档，编程后全量HEX回读通过，两台316保持V12.56并核对原图像一致。"
        f"本轮{len(main_test['cases'])}项主流程和{len(electric['cases'])}项电加热归属／正常恢复检查通过，最终参数与保存缓存核对通过。"
        "未测量实体端子电压、水阀实际行程，本次也未做物理断电；这些不包含在板上软件输出验收内。")
    text+='''

## 2026-11-24烧录及板测记录

- 烧录前确认330停机、所有执行输出关闭、故障为0；备份330完整512KB内部Flash与128KB SRAM，以及原参数。只烧录330，随后校验三块板的代码图像与正式档参数。
- 制冷／制热分别验证手动0、100、300、500、1000，925、922、DA8及实际PWM比较寄存器一致。PWM驱动满量程980，属于驱动指令证据，不能替代万用表测量。
- 制冷／制热分别验证新风−0.1℃、0℃、+0.1℃；只有低于0℃时应用346最小值。手动值高于最小值时不被降低；346为0时禁用最小值，346为1000时输出满量程；247始终保留手动值。
- 室温22℃、27℃、25℃变化及旧246设置变化不改变DA8手动输出；尝试245旧自动值后仍固定手动1。
- 新风NTC2以原始采集值32767模拟失效，固件自行报330[600]、置Y05软件输出为1、置传感器保护并关闭DA8；恢复原始采集输入及普通故障复位后手动开度恢复。未写故障字、输出字或派生温度。
- 主测试停止后另启用电加热AO和电预热AO，在室温25℃、制热设定15℃、新风−0.1℃且预热温区−10～−20℃的无加热需求条件下，覆盖电热主加热、热泵共享／独立辅助加热配置，DA0／DA1／DA9均为0，只有DA8执行20%最小开度。此前ARM回归同时核对了正常电热PID未改变。
- 停机通过398普通停机命令，完整走原有停机与风阀收尾；不使用急停、输出强写或改计时跳过等待。室内外DO、DA8及PWM均记录时间戳；本项没有请求压机加载，全部采样中两台316压机GPIO均保持0。
- 原始输入模拟只写NTC0／1／2的采集缓冲和原始滤波数组，程序持续运行；实际温度回读必须稳定到目标再判定。退出时撤销模拟，恢复本轮所有临时参数。

最终状态：330 V10.74／两台316 V12.56，正式档标记0，最短停机120秒、最短运行180秒、环温确认1298=300秒，未更改这些时序。330[247]恢复500、[346]恢复0，因此当前最小开度功能未启用；[245]按新版本归一为手动1。其余设置相对烧录前没有非预期变化，普通停机完成，故障及Y05软件输出均为0。保存缓存与本轮触及参数一致、保存状态空闲；不将此项宣称为实际断电验证。

原始记录：deployment.json、board_manual.json、board_electric_separation.json、对应逐样本JSONL、final_audit.json、trace_inventory.json。历史离线夹具失败证据继续保留。
'''
    report.write_text(text,'utf8')
    scripts=['deploy_da8_manual_v1074_20261124.py','board_da8_manual_v1074_20261124.py',
        'board_da8_electric_separation_20261124.py','audit_da8_v1074_20261124.py','report_da8_v1074_20261124.py']
    for filename in scripts:shutil.copy2(dep.R/'tools'/filename,day/filename)
    print('DA8 REPORT FINALIZED',scope['board_cases'],'board checks; traces',traces,flush=True)


if __name__=='__main__':main()
