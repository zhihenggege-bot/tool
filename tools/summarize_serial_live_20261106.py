"""Report restored COM6-only cases without converting them to physical passes."""
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'测试证据/内机实测_20261105/BENCH_V1053_V1239'


def main():
    manifest=json.loads((BASE/'remaining_571_manifest.json').read_text('utf8'))
    names={r['用例编号']:r['测试名称'] for r in manifest['cases']}
    completed={};attempts=[];running=[]
    for path in sorted(BASE.glob('remaining571_heat_dynamic_serial_*_20261106_*.json')):
        data=json.loads(path.read_text('utf8'))
        source=path.relative_to(ROOT).as_posix()
        attempts.append(dict(source=source,restored=data.get('restored'),error=data.get('error'),
            interrupted=data.get('interrupted_by_test_supervisor'),cases=list(data.get('cases',{}))))
        if data.get('restored') is not True or data.get('cleanup_error'):
            running.append(source);continue
        if data.get('error') or data.get('interrupted_by_test_supervisor'):continue
        for cid,case in data.get('cases',{}).items():
            if not isinstance(case,dict) or case.get('passed') is not True or case.get('error'):continue
            # These are successful declared software subchecks, not a blanket
            # acceptance of the full original test-plan row.
            completed[cid]=dict(id=cid,name=names.get(cid,cid),source=source,
                result='软件子项匹配；整项部分通过',version=data.get('versions'),
                debug_port_used=data.get('debug_port_used'),
                physical_terminal_measurement=data.get('physical_terminal_measurement'))
    report=dict(scope='本轮COM6-only续测；未覆盖端子/真实断电/正式档，不能当作完整验收通过',
        unique_software_subchecks=len(completed),groups=dict(Counter(cid.split('-')[0] for cid in completed)),
        cases=[completed[k] for k in sorted(completed)],attempts=attempts,unfinished_sources=running,
        board_firmware='330 V10.53 / 316 V12.39 BENCH',
        source_fix='V10.54两档已构建、30组ARM回归通过，尚未烧录，远程恢复修复未作板上通过。')
    (BASE/'serial_completed_summary_20261106.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    lines=['# 内机串口续测结果（2026-11-06）','',report['scope']+'。','',
        f'板上：{report["board_firmware"]}。已恢复批次中，共{len(completed)}个用例取得本次声明范围的软件证据。',
        '',report['source_fix'],'',
        '勾选只表示所列软件子项已执行，具体刺激、时序与局限见原始日志。旧脚本异常和中断记录保留，不计通过。','',
        '|执行|用例|项目|结果|证据|','|---|---|---|---|---|']
    for cid,c in sorted(completed.items()):
        lines.append(f'|[x]|{cid}|{c["name"]}|{c["result"]}|[原始日志]({c["source"]})|')
    lines+=['','## 未计通过的尝试','',
        '- 首次600秒：切换已启动，旧脚本错误地要求5秒内模式寄存器更新；后续分别验证启动边沿及制冷建立。',
        '- 首次1200秒：监督停止旧脚本时已经启动；该次中断，随后正常停机、按原始快照恢复，重新整轮测试。',
        '- 旧特殊模式SWD采集异常及消毒/排毒远程恢复失败保留；本次五项自动消排毒保护不覆盖远程自动恢复。',
        '- 17:00的两例组合故障尝试因AI1无效，在前置输出建立阶段结束，尚未注入组合故障；分类为环境受限，原始异常保留。后续无控湿配置只签主热/预热等已声明的软件范围。','',
        '## 尚未覆盖','',
        '- 物理端子电压/接点、真实断电、正式档时序。',
        '- YS本批验证许可及公开诊断；私有PID余数逐拍公式不据此验收。',
        '- 高温边界本批验证主热及独立再热各自运行；31.25℃精确等号、低温满开边界、冬季−1℃叠加仍缺条件，不据此验同时运行。',
        '- 环境制冷本批验证目标数量公式，不代表每个点的压机反馈已收敛。',
        '- 无控湿配置的组合故障测试未验证加湿从有输出到切断及恢复；正常模式切换只验公开退出/启动状态，不宣称已读取私有活动/待切模式。']
    if running:lines+=['','仍未取得恢复标记的日志：']+[f'- [{Path(p).name}]({p})' for p in running]
    (ROOT/'内机串口续测结果_20261106.md').write_text('\n'.join(lines)+'\n','utf8')
    print(json.dumps(dict(unique_software_subchecks=len(completed),unfinished=len(running)),ensure_ascii=False))


if __name__=='__main__':main()
