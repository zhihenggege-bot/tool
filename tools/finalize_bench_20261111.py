"""Reconcile observed scopes and explicit limitations without inventing passes."""
import csv
import json
import time
from pathlib import Path
from collections import Counter
from record_bench_queue_20261111 import publish,ROOT,DAY,QUEUE


def run():
    publish()
    audit_dir=ROOT/'测试证据/机型风机全局共享_20261110'
    latest=max(audit_dir.glob('independent_audit_*.json'),key=lambda p:p.stat().st_mtime)
    audit=json.loads(latest.read_text('utf8'))
    assert audit.get('passed') and all(audit['checks'].values()),'Final recovery audit not passed'
    assert time.time()-latest.stat().st_mtime<180,'Final recovery audit must be fresh'
    (DAY/'final_independent_readback.json').write_bytes(latest.read_bytes())
    with QUEUE.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
    assert len(rows)==306
    for r in rows:
        if r['用例']=='O-LINK-006':
            r.update({'执行状态':'软件子范围通过','结果':'本批所有实际执行后的三板独立核验通过；版本、HEX逐字节、源码清单、参数、停机输出、故障及化霜占用均核验。真实端子另验。',
                '新证据':'测试证据/台架执行_20261111/final_independent_readback.json','恢复核验':'最终独立三板读回全部检查通过'})
        if r['用例']=='T17-004':
            r.update({'执行状态':'盘点完成','结果':'306行逐项保留执行证据、范围和剩余项；盘点完成不等于未测项通过。',
                '新证据':'测试证据/台架执行_20261111/queue_summary.json','恢复核验':'见最终独立三板回读'})
        if r['执行状态']!='待执行':continue
        batch=r['批次'];cid=r['用例'];reason=None
        if batch.startswith('C01'):
            reason='当前仅一台330、两台316；第三/第四外机及5～8回路安装条件不足。当前模拟不能替代扩展硬件验收。'
        elif batch.startswith('C02'):
            reason='未取得实际电压/电流/温度源及端子仪表记录；软件换算或显示回读不计物理测量。'
        elif batch.startswith('C03') or cid=='T10-024':
            reason='当前无可控真实断电工装；不使用调试器复位代替掉电和EEPROM持久化验收。'
        elif cid in ('T10-017','T10-025','T10-026','T10-027','O-LINK-005','O-DEFROST-021'):
            reason='未建立330—316真实分路断链与恢复工装；不通过停CPU或写通讯故障位伪造断链。'
        elif cid in ('T06-002','T06-003','T06-005','T06-006'):
            reason='当前接口仅选择AO/分级/SCR输出，未提供独立蒸汽/热水介质枚举，也无对应阀门分别安装及接线仪表确认；共同AO测试不替代四项独立介质验收。范围依据：测试证据/台架执行_20261111/介质及真实断链验收范围.md。'
        elif cid in ('O-PARAM-025','O-PARAM-026'):
            reason='需要可恢复首次初始化/空白EEPROM条件；本批保留现有配置，不擦除EEPROM。'
        if reason:
            r.update({'执行状态':'条件受限','结果':reason,'恢复核验':'本批未为此项目施加输入或改变配置'})
        elif batch.startswith('B08'):
            r.update({'执行状态':'正式档未执行','结果':'当前板上BENCH_ONLY_3S；本轮未烧录PRODUCTION，不把BENCH轨迹计为正式秒数验收。','恢复核验':'保持当前已核验版本'})
    tmp=QUEUE.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    tmp.replace(QUEUE)
    counts={unit:dict(Counter(r['执行状态'] for r in rows if r['机组']==unit)) for unit in ('330','316')}
    issues=[]
    for path in sorted(DAY.glob('*.json')):
        try:d=json.loads(path.read_text('utf8'))
        except (ValueError,OSError):continue
        if not isinstance(d,dict):continue
        for section in ('fixed_vfd','fan_curves','ambient','defrost_natural','priority_case','continuation_case','remaining_functional','parameter_matrix','B01','B01_contacts'):
            e=d.get(section,{})
            if not e:continue
            if e.get('execution_error') or e.get('error'):
                issues.append(dict(evidence=path.relative_to(ROOT).as_posix(),type='用例前置或执行异常',detail=(e.get('execution_error') or e['error']).splitlines()[-1]))
            for p in e.get('points',[]):
                if p.get('behavior_matches') is False or p.get('matches') is False or p.get('passed') is False:
                    issues.append(dict(evidence=path.relative_to(ROOT).as_posix(),type='观察差异，须核对完整前置',detail=p.get('label',str(p.get('temp10')))))
            case_rows=e.get('cases',[])
            if isinstance(case_rows,list):
                for row in case_rows+e.get('events',[]):
                    if row.get('passed') is False or row.get('error') or row.get('status') in ('实测有待核对','实测条件未建立或采样异常'):
                        issues.append(dict(evidence=path.relative_to(ROOT).as_posix(),type='逐项差异或前置异常，保留复测证据',
                            case=row.get('id'),detail=row.get('error') or row.get('label') or row.get('status')))
    summary=dict(at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),counts=counts,rows=306,
        complete_acceptance_claimed=False,firmware_changed=False,issues=issues,
        pending=[r for r in rows if r['执行状态']=='待执行'],
        evidence_scope='Current BENCH board input simulation and software outputs; physical terminals, real power loss, extension boards and production timing separate')
    (DAY/'queue_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# 11月11日内外机台架执行盘点','',
        '版本：330 V10.58 / 316 V12.40，BENCH_ONLY_3S。固件未修改、未烧录。以下按实际证据统计，子范围与整项验收分开。','',
        '|机组|执行状态|行数|','|---|---|---:|']
    for unit,items in counts.items():
        lines.extend(f'|{unit}|{status}|{count}|' for status,count in items.items())
    lines+=['','306行原队列保持完整。仍为待执行的项目不能解释为通过或受限，需继续安排。',
        '',f'当前待执行：{len(summary["pending"])}行。问题及前置异常原始记录见[盘点JSON](测试证据/台架执行_20261111/queue_summary.json)。',
        '', '所有结果见[逐项队列](内外机台架测试队列_20261111.csv.txt)。参数恢复以各批恢复记录和三板独立核验为准；最初1/3前置异常、压力下限残留及随后撤源/回读纠正记录均保留。',
        '', '36℃按用户当前口径保持；图转录差异单列，本批不改固件。DA8的独立介质许可和未明确的流程边界不由测试工具补定。']
    (ROOT/'台架执行盘点_20261111.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps(dict(counts=counts,pending=len(summary['pending']),issues=len(issues)),ensure_ascii=False,indent=2))


if __name__=='__main__':run()
