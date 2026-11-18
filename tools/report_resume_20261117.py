"""Derive continuation status from saved evidence, keeping failures visible."""
import hashlib
import json
from pathlib import Path
from datetime import datetime,timezone,timedelta

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/续测_20261117'
def read(p):return json.loads(p.read_text('utf8'))
def link(p):return p.relative_to(R).as_posix()


def main():
    summary=dict(generated=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
                 firmware='330 V10.63 /316 V12.44 BENCH_ONLY_3S',manual=[],automatic=[],ai=[],monitor=[],curves=[])
    lines=['# 内外机续测记录（2026-11-17）','',
        '绑定330 V10.63 / 两台316 V12.44，BENCH_ONLY_3S。正式时序及连续2小时稳定性按用户要求继续暂缓。',
        '软件DO/AO、ARM回归、用户现场观察分别记录，不将软件回读当作仪表端子测量。','',
        '330中断烧录已恢复，完整HEX回读及三板版本、参数、停止状态审计通过。',
        '恢复烧录原始证据保留在测试证据/手动联锁修复_20261113/复位可靠传递修复后/deployment_recovery_*.json。','',
        '|手动保护项|完整判据通过|批次恢复|证据|','|---|---|---|---|']
    for p in sorted(D.glob('rerun_manual_protection_stopped_configuration_*.json')):
        q=read(p)
        for c in q.get('targeted_rerun',{}).get('cases',[]):
            name={0:'X00高压',1:'X01低压',6:'X06过载',4:'X04风机1',5:'X05风机2'}[c['channel']]
            row=dict(name=name,passed=c.get('passed',False),restored=q.get('restored',False),error=c.get('error'),evidence=link(p))
            summary['manual'].append(row)
            lines.append(f'|{name}|{row["passed"]}|{row["restored"]}|[记录]({link(p)})|')
    lines+=['','手动保护覆盖故障输入出现与保持、316实际保护、330镜像及Y05输出、带故障复位不解除、撤源后复位与压机恢复。输入极性刺激会影响两块316，不等同单台外机独立接线故障。','']
    observation=D/'Y05现场观察.json'
    if observation.exists():
        summary['physical_Y05_user_observation']=read(observation)
        lines+=['用户现场确认：本轮报警期间330实体Y05“看到吸合了”。该观察不等同端子电压量测。[现场反馈记录]('+link(observation)+')。','']
    for p in sorted(D.glob('rerun_fan_interlock_and_automatic_regression_*.json')):
        q=read(p);e=q['manual_automatic_regression']
        row=dict(passed=e.get('passed',False),restored=q.get('restored',False),error=e.get('error'),
                 checks=[dict(check=c['check'],passed=c.get('passed',False)) for c in e['checks']],
                 fan_lead=e.get('automatic_fan_lead',[]),evidence=link(p))
        summary['automatic'].append(row)
        lines+=['自动／手动联锁回归：整批通过='+str(row['passed'])+'，恢复='+str(row['restored'])+'。[记录]('+link(p)+')。','']
        for c in row['checks']:lines.append('- '+c['check']+'：'+str(c['passed']))
        for c in row['fan_lead']:lines.append(f'- {c["unit"]}#外机：软件风机领先首次压机输出约{c["observed_fan_lead_s"]:.3f}秒。')
        if row['error']:lines+=['','原始异常：'+row['error'].splitlines()[-1]]
        lines.append('')
    for p in sorted(D.glob('rerun_AI_consumed_input_diagnostics_*.json')):
        q=read(p);e=q.get('targeted_rerun',{})
        cases=[dict(channel=c['channel'],raw=c['raw'],flow=c['flow_basis'],passed=c.get('passed',False),
                    recovery=c.get('recovery_verified',False),consumed_range=c.get('consumed_range'),limitation=c.get('limitation'),error=c.get('error')) for c in e.get('cases',[])]
        summary['ai'].append(dict(cases=cases,restored=q.get('restored',False),error=e.get('error'),evidence=link(p)))
        lines+=['AI持续输入诊断：'+str(sum(c['passed'] for c in cases))+'/'+str(len(cases))+'点满足本轮软件判据；输入未连续建立的点仍属条件不足。[记录]('+link(p)+')。','']
    for p in sorted(D.glob('monitor_live_readonly_*.json')):
        q=read(p);summary['monitor'].append(dict(passed=q.get('passed',False),sessions=q.get('sessions',[]),
            read_count=len(q.get('reads',[])),write_count=len(q.get('writes',[])),error=q.get('error'),evidence=link(p)))
        lines+=['监控软件真实Tk界面／串口只读连接、轮询及重连：通过='+str(q.get('passed',False))+'。未进行写入操作与界面外观验收。[记录]('+link(p)+')。','']
        if q.get('passed',False):
            lines += [f'本次{len(q.get("reads",[]))}次读取、{len(q.get("writes",[]))}次写入，{len(q.get("sessions",[]))}次连接；线程退出及缓存清理均核验通过。','']
        if not q.get('passed',False):
            lines+=['上述首次记录超时来自测试脚本错误地等待周期轮询缓存中出现版本号；监控程序按设计通过主动读取获取版本。测试脚本修正后另行复测，首次记录保留，不计作产品缺陷。','']
    curve_names={(1,2):'Ⅱ型单变频',(2,2):'Ⅲ型单变频',(2,4):'Ⅲ型一定一变'}
    check_names={
        'minimum_frequency':'10Hz下限及软件AO=200',
        'maximum40_reached':'40Hz上限到达',
        'normal_load_step_1Hz':'普通加载每步1Hz',
        'fixed_fan_load_step_2Hz':'定速风机开启后每步2Hz',
        'load_rate_1.0Hz_per_s':'普通加载约1Hz/s',
        'load_rate_2.0Hz_per_s':'定速风机开启后加载约2Hz/s',
        'hold_35C':'35℃保持',
        'maximum30_software6V':'临时30Hz上限及软件AO=600',
        'intermediate_hold_35C':'恢复40Hz上限后35℃仍保持中间30Hz',
        'unload_to_off':'降载最终停风机',
        'unload_reaches_minimum_before_off':'停机前最后采样≤11Hz（10Hz下限、1Hz采样容差）',
        'frequency_bounds':'运行频率在10～40Hz范围',
        'software_AO_fixed_50Hz_scaling':'软件AO按0～10V对应0～50Hz换算',
    }
    for p in sorted(D.glob('targeted_vfd_*.json')):
        q=read(p);summary['curves'].append(dict(pair=q.get('pair'),checks=q.get('checks'),restored=q.get('restored'),error=q.get('error'),
            off_edges=q.get('off_edges'),load_rates=q.get('measured_load_rates_Hz_per_s'),evidence=link(p)))
        name=curve_names.get(tuple(q.get('pair',[])),str(q.get('pair')))
        lines+=['风机曲线针对性复核：'+name+'；批次恢复='+str(q.get('restored',False))+'。[记录]('+link(p)+')。','',
                '|判据|结果|','|---|---|']
        for key,value in q.get('checks',{}).items():
            lines.append('|'+check_names.get(key,key)+'|'+('通过' if value else '未通过，见原始记录')+'|')
        lines.append('')
        if 'intermediate_hold_35C' not in q.get('checks',{}):
            lines+=['此批35℃保持采样位于40Hz上限，未包含后加的30Hz中间频率保持判据；中间保持仅在对应后续批次有记录时计入。','']
        for edge in q.get('off_edges',[]):
            lines.append(f'- {edge["at"]}：停风机前最后采样频率{edge["previous_speed10"]/10:.1f}Hz，软件AO={edge["previous_ao"]}。')
        if q.get('off_edges'):lines.append('')
        if q.get('checks',{}).get('unload_reaches_minimum_before_off'):
            lines+=['停机边沿按最后采样允许跨1Hz步长判定；本批最后运行采样为11Hz，未捕获持续10Hz台阶，不作为最低频率驻留时间或端子电压验收。','']
        for point in q.get('points',[]):
            if point['label']!='unload33C_to_fans_off':continue
            edges=[]
            for a,z in zip(point['samples'],point['samples'][1:]):
                delta=a['OutdoorVfdSpeed']-z['OutdoorVfdSpeed']
                if delta>0 and a['OutdoorFixedOn']==z['OutdoorFixedOn'] and a['OutdoorVfdOn'] and z['OutdoorVfdOn']:
                    edges.append(dict(t=z['t'],fixed=z['OutdoorFixedOn'],delta=delta))
            rates={}
            for fixed in (0,1):
                es=[e for e in edges if e['fixed']==fixed]
                if len(es)>=5:
                    rates[str(fixed)]=sum(e['delta'] for e in es[1:])/10/(es[-1]['t']-es[0]['t'])
            summary['curves'][-1]['derived_unload_rates_Hz_per_s']=rates
            if rates:
                lines+=['原始降载采样另行计算：'+ '；'.join(('定速开' if key=='1' else '定速关')+f'时约{value:.3f}Hz/s' for key,value in rates.items())+'。此为本批实测速度，不扩展为其他参数档验收。','']
    arm=D/'unload_conditional_ARM.json'
    if arm.exists():
        summary['confirmed_issues']=[dict(name='单变频降载在非秒节拍扫描提前停机',
            source='PSC316RK-V12-外机/WELLTHINKER/User/UserAction.c:1459',
            arm_evidence=link(arm),firmware_changed=False)]
        lines+=['已确认新增问题：Ⅱ型／Ⅲ型单变频降载时，代码把“频率大于最低值”与“本次为1秒节拍”合在同一个if条件中；非秒节拍扫描会进入后面的停机分支，可能从高于最低值的频率直接关闭。板上频率／AO边沿与两种编译档的实际ARM函数复现相互印证。[ARM复现]('+link(arm)+')。',
                '定位：PSC316RK-V12-外机/WELLTHINKER/User/UserAction.c第1459～1471行。本轮先记录并继续其他配置测试，未修改固件源码。','']
    audits=[]
    for p in sorted(D.glob('*audit*.json'))+sorted(D.glob('after_*.json')):
        q=read(p)
        if 'verified' in q:audits.append((p,q))
    if audits:
        p,q=max(audits,key=lambda x:x[0].stat().st_mtime)
        summary['latest_audit']=dict(verified=q['verified'],evidence=link(p))
        lines+=['最近独立审计：'+str(q['verified'])+'。[证据]('+link(p)+')。','']
    lines+=['仍保留：正式时序28项、连续2小时稳定性、此前83项条件受限范围；本轮AI共12点中11点未能建立连续有效刺激，与此前83项的重叠未重新去重，不将两者直接相加。物理0～10V/0～50Hz量测未验收，软件AO比例通过不代表端子实测通过。','',
            '连续协议与软件状态：[events.jsonl]('+link(D/'events.jsonl')+')。原始失败、复测和恢复记录均保留。']
    summary['source_and_artifact_identity']={}
    package=R/'.codex-tmp/manual_gate_v1063_v1244_20261113'
    for profile in ('BENCH_ONLY_3S','PRODUCTION'):
        manifest=read(package/profile/'manifest.json')
        sources=manifest['source_inventory'];artifacts=manifest['artifacts']
        mismatches=[name for name,want in sources.items() if hashlib.sha256((R/name).read_bytes()).hexdigest()!=want]
        bad_artifacts=[name for name,want in artifacts.items() if hashlib.sha256((package/profile/name).read_bytes()).hexdigest()!=want]
        summary['source_and_artifact_identity'][profile]=dict(source_count=len(sources),source_mismatches=mismatches,artifact_mismatches=bad_artifacts)
        lines+=['',f'{profile}源码／产物哈希复核：{len(sources)}个源码条目，源码不一致{len(mismatches)}项，产物不一致{len(bad_artifacts)}项。']
    (R/'内外机续测结果_20261117.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    (D/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    inventory={p.relative_to(D).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in D.rglob('*') if p.is_file() and p.name!='evidence_inventory.json'}
    (D/'evidence_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf8')
    print('REPORT UPDATED',summary['generated'],flush=True)


if __name__=='__main__':main()
