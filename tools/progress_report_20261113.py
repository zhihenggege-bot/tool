"""Read saved journals only. Execution count never implies acceptance count."""
from pathlib import Path
import json
import time
R=Path(__file__).resolve().parents[1]
D=R/'测试证据/逐项测试_20261113'
def read(p):
    try:return json.loads(p.read_text('utf8'))
    except (OSError,ValueError):return {}
def summarize():
    controller=read(D/'controller.json')
    result=dict(at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),status=controller.get('status'),active=controller.get('active'),
        planned_bench_batches=len(controller.get('tasks',[])),executed_bench_batches=len(controller.get('executed',[])),
        deployment_verified=bool(read(D/'deployment_counter_review.json').get('verified')),cases=[],errors=[])
    for p in sorted(D.glob('*.json')):
        q=read(p)
        if not isinstance(q,dict):continue
        e=q.get('regression')
        if isinstance(e,dict):
            result['cases'].append(dict(evidence=p.relative_to(R).as_posix(),unit=e.get('unit'),verdict=e.get('verdict','执行中或未完成'),
                restored=q.get('restored',False),error=e.get('error'),fixed_page_hold=e.get('fixed_page_hold'),finished=e.get('finished')))
        for section in ('remaining_functional','ambient','manual_contact_protection','fixed_vfd'):
            obj=q.get(section)
            if not isinstance(obj,dict):continue
            for row in obj.get('cases',obj.get('points',[])):
                notes=[]
                if obj.get('kind') in ('outdoor_pressure_ADC','indoor_ADC_ventilation'):
                    ch=row.get('channel',0)+(3 if obj.get('kind')=='indoor_ADC_ventilation' else 0)
                    raw=row.get('raw',0)
                    values=[s['adc'][ch] for s in row.get('samples',[]) if len(s.get('adc',[]))>ch]
                    if values and not all(v==raw for v in values):
                        notes.append(f'ADC目标{raw}仅{values.count(raw)}/{len(values)}帧相符；报警/保护轨迹保留，输入连续性不足，不计完整输入验收')
                result['cases'].append(dict(evidence=p.relative_to(R).as_posix(),section=section,
                    id=row.get('id'),label=row.get('label'),restored=q.get('restored',False),
                    review_notes=notes,
                    observations={k:row[k] for k in ('passed','matches','status','error','verdict','software_scope_passed') if k in row}))
            if obj.get('error') or obj.get('execution_error'):result['errors'].append(dict(evidence=p.relative_to(R).as_posix(),error=obj.get('error',obj.get('execution_error'))))
    formal=read(D/'PRODUCTION/controller.json');follow=read(D/'formal_followup_controller.json')
    result['formal']=dict(status=formal.get('status','未执行'),executed=len(formal.get('executed',[])),tasks=len(formal.get('tasks',[])),active=follow.get('active'))
    lines=['# 内外机逐项测试进度（2026-11-13）','',f"更新：{result['at']}。状态：{result['status']}。",'',
        '烧录与回读：330 V10.61已升级，两台316 V12.43已逐段核对；保存参数核验见deployment_counter_review.json。',
        '当前BENCH功能回归与正式秒数分开。输入为板上ADC/极性模拟，DO/AO为软件回读，实际端子另测。', '',
        f"主队列：{result['executed_bench_batches']}/{result['planned_bench_batches']}批执行并恢复审计；R01独立先行，不混入此批数。当前：{(result['active'] or {}).get('key','无活动批次')}。",'',
        '批次执行、退出码及整项验收合格分别记录。普通问题保留证据，恢复核验后继续；恢复未核验时先处理恢复。', '',
        '|项目/证据|观察结论|恢复|','|---|---|---|']
    for c in result['cases']:
        detail=c.get('verdict') or str(c.get('observations'))
        if c.get('review_notes'):detail+='；'+'；'.join(c['review_notes'])
        if c.get('error'):detail+='；'+c['error'].splitlines()[-1]
        detail=detail.replace('|','/').replace('\n',' ')[:450]
        lines.append(f"|[{Path(c['evidence']).stem}]({c['evidence']})|{detail}|{c['restored']}|")
    lines+=['',f"正式队列：{result['formal']}。2小时稳定性单独计时；83项受限复核见本日条件复核清单。"]
    for p,raw in [(D/'progress.json',json.dumps(result,ensure_ascii=False,indent=2)),(R/'逐项测试进度_20261113.md','\n'.join(lines)+'\n')]:
        t=p.with_suffix('.tmp');t.write_text(raw,encoding='utf8');t.replace(p)
    return result
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--watch',action='store_true');a=p.parse_args()
    while True:
        q=summarize()
        if not a.watch:print(json.dumps(q,ensure_ascii=False,indent=2));break
        if read(D/'formal_followup_controller.json').get('status') in ('scheduled_batches_executed_review_per_case_results','paused_by_user'):break
        if q['status']=='restoration_or_controller_error':break
        time.sleep(15)
