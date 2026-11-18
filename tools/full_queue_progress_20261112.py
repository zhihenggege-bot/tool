"""Read journals only and publish current execution counts without inventing passes."""
from pathlib import Path
import json
import time
import os
R=Path(__file__).resolve().parents[1]
D=R/'测试证据/剩余全队列_20261112'

def review_case(section, obj, row):
    """Qualify recorded verdicts using their actual input/observation scope."""
    notes=[]
    extra={}
    if section=='fixed_vfd':
        samples=row.get('samples',[])
        exact=row.get('first_exact_t')
        observed=[s for s in samples if exact is not None and s.get('t',0)>=exact]
        speeds=[s['OutdoorVfdSpeed'] for s in observed if 'OutdoorVfdSpeed' in s]
        if exact is not None and row.get('requested_t') is not None:
            extra['input_setting_and_settling_s']=round(exact-row['requested_t'],3)
        if row.get('kind')=='hold' and speeds:
            extra['all_sample_frequency_hold']=len(set(speeds))==1
        if row.get('label')=='35C_intermediate_hold' and not obj.get('intermediate_established'):
            notes.append('未建立中间频率，不能关闭中间频率保持验收项')
        if obj.get('pair',[None,None])[1]==4 and '36C' in row.get('label',''):
            notes.append('36℃图文边界用户暂缓修改，仅记录实际轨迹')
        if row.get('kind')=='observe':
            notes.append('观察轨迹，无明确整项通过判据')
        if row.get('label')=='45_1C_after_verified_off' and observed and observed[0].get('OutdoorVfdOn'):
            notes.append('两路45.1℃输入稳定时变频风机已开；未证明停风且温度>45℃的同时前提，不能据此判未满频缺陷')
    if section=='remaining_functional' and obj.get('kind')=='indoor_ADC_ventilation':
        ch=row.get('channel',0)
        raw=row.get('raw')
        samples=row.get('samples',[])
        actual=[s['adc'][ch+3] for s in samples if len(s.get('adc',[]))>ch+3]
        if raw is not None and actual:
            extra['requested_raw_observed_samples']=sum(v==raw for v in actual)
            extra['raw_samples']=len(actual)
            extra['actual_raw_range']=[min(actual),max(actual)]
            if not all(v==raw for v in actual):
                notes.append('请求ADC值未在全部回读样本持续建立；保留报警观察，输入连续性不足，不能判固件缺陷或完整通过')
        if not row.get('passed'):
            notes.append('本次未建立诊断前提；保留为待补测')
    if row.get('label')=='different_unit' and row.get('passed') is False:
        notes.append('后续紧邻请求仍未证明第二请求抵达时第一请求未完成；冲突前提不足，非已确认固件缺陷')
    if row.get('id')=='T06-025':
        notes.append('DA8为既有介质/权限未决观察，不能按单次指令不一致判新缺陷')
    return dict(**extra,review_notes='；'.join(notes)) if notes or extra else {}

def summarize():
    p=D/'controller.json';q=json.loads(p.read_text('utf8'))
    data=dict(at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),status=q['status'],
        batch_total=len(q['tasks']),batches_executed_and_restoration_audited=len(q['executed']),
        remaining_batches=len(q['tasks'])-len(q['executed']),active=q.get('active'),
        execution_errors=[x for x in q['executed'] if x['exitcode']],cases=[],
        note='Batches are not acceptance cases. Explicit software results only; physical terminal and unavailable conditions remain open.')
    formal=D/'PRODUCTION/controller.json'
    if formal.exists():
        fq=json.loads(formal.read_text('utf8'))
        data['production']=dict(status=fq['status'],batches_executed=len(fq['executed']),
            batches_total=len(fq['tasks']),latest_step=fq['steps'][-1] if fq['steps'] else None)
    for path in sorted(D.glob('*.json')):
        try:raw=json.loads(path.read_text('utf8'))
        except (OSError,ValueError):continue
        if not isinstance(raw,dict) or not raw.get('original') or 'restored' not in raw:continue
        for section in ('remaining_functional','parameter_matrix','manual_contact_protection','gateway_recheck','fixed_vfd','ambient','B01_contacts'):
            obj=raw.get(section)
            if not isinstance(obj,dict):continue
            rows=list(obj.get('cases',obj.get('points',[])))+list(obj.get('events',[]))
            for row in rows:
                if not isinstance(row,dict):continue
                verdict={key:row[key] for key in ('id','label','parameter','passed','software_scope_passed','matches','behavior_matches','observed_matches_command','error','verdict') if key in row}
                if not verdict:continue
                data['cases'].append(dict(**verdict,**review_case(section,obj,row),section=section,evidence=path.relative_to(R).as_posix(),batch_restored=raw.get('restored')))
        for cid,row in raw.get('current_records',{}).items():
            data['cases'].append(dict(id=cid,passed=row.get('passed'),review_notes=row.get('detail',''),
                section='current_records',evidence=path.relative_to(R).as_posix(),batch_restored=raw.get('restored')))
    formal_rows=[]
    for path in sorted((D/'PRODUCTION').glob('*.json')):
        try:raw=json.loads(path.read_text('utf8'))
        except (OSError,ValueError):continue
        if not isinstance(raw,dict):continue
        entry=raw.get('formal_timing')
        if isinstance(entry,dict):
            formal_rows.append(dict(ids=entry.get('ids',[]),executed=entry.get('executed',False),
                full_acceptance=entry.get('full_acceptance',False),restored=raw.get('restored',False),
                error=entry.get('error'),remaining=entry.get('remaining',entry.get('scope','')),
                evidence=path.relative_to(R).as_posix()))
    data['formal_case_scopes']=formal_rows
    target=D/'progress.json';tmp=target.with_suffix(f'.{os.getpid()}.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(target)
    active=data['active']['key'] if data['active'] else '无活动批次'
    if data.get('production'):active+='；正式档：'+str(data['production'])
    text=['# 剩余全队列执行进度（2026-11-12）','',
        f"更新：{data['at']}。状态：{data['status']}。",'',
        f"原53批已执行并完成独立恢复审计{len(q['executed'])}批，尚未完成{data['remaining_batches']}批；当前：{active}。",'',
        '当前BENCH为330 V10.60 /两316 V12.43。先做短批，再做较长风机/化霜批；随后切换同版三板PRODUCTION进行正式时序，最后完整连续2小时通风通讯/软件输出稳定性观察。原28行正式时序清单单独保留。', '',
        '计数是执行批次，不是整项验收合格数。脚本退出码0不代表该批每个用例通过。软件输出不代替实际端子测量，BENCH不代替正式秒数。83项条件受限保留原原因。', '',
        '|项目|观察/结论|证据|','|---|---|---|']
    for c in data['cases']:
        name=c.get('id',str(c.get('parameter',c.get('label',''))))
        details='；'.join(f'{k}={v}' for k,v in c.items() if k not in ('id','evidence','section','batch_restored'))
        details=details.replace('|','/').replace('\n',' ')[:450]
        text.append(f"|{name}|{details}|[{Path(c['evidence']).name}]({c['evidence']})|")
    if formal_rows:
        text+=['','正式档逐例范围（执行不代表全部条款验收通过）：','','|项目|执行/恢复/剩余范围|证据|','|---|---|---|']
        for row in formal_rows:
            detail=f"executed={row['executed']}；restored={row['restored']}；full_acceptance={row['full_acceptance']}；{row['remaining']}"
            if row['error']:detail+='；error='+row['error'].splitlines()[-1]
            text.append(f"|{','.join(row['ids'])}|{detail.replace('|','/')}|[{Path(row['evidence']).name}]({row['evidence']})|")
    report=R/'剩余全队列执行进度_20261112.md'
    temp=report.with_suffix(f'.{os.getpid()}.tmp');temp.write_text('\n'.join(text)+'\n',encoding='utf8');temp.replace(report)
    return {k:v for k,v in data.items() if k!='cases'}

if __name__=='__main__':print(json.dumps(summarize(),ensure_ascii=False,indent=2))
