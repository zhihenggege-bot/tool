"""Publish current-image subscopes without overwriting old failure evidence."""
from pathlib import Path
import csv,datetime,io,json
ROOT=Path(__file__).resolve().parents[1]
DAY=ROOT/'测试证据/修复后内外机联合实测_20261110'

def latest(pattern):
    for p in sorted(DAY.glob(pattern),reverse=True):
        try:
            j=json.loads(p.read_text('utf8'));j['_evidence_path']=str(p.resolve());return p,j
        except (OSError,ValueError):continue
    return None,None

def main():
    updates={};lines=[]
    def add(ids,status,detail,p):
        lines.append((ids,status,detail,p))
        for cid in ids:updates[cid]=dict(status=status,detail=detail,path=p)
    def restored(j):
        if not j:return False
        if j.get('restored') and not any(j.get(k) for k in ('today_cleanup_error','cleanup_error','restore_mismatches')):return True
        # An interrupted writer stays untouched. Accept recovery only with a
        # separate restoration record AND a later independent all-pass audit.
        for p in DAY.glob('independent_restore_*.json'):
            try:r=json.loads(p.read_text('utf8'))
            except (ValueError,OSError):continue
            if not r.get('restored') or str(Path(r['source']).resolve())!=j.get('_evidence_path'):continue
            _,a=latest('final_independent_readback_*.json')
            if a and a.get('passed') and a['started']>=r['finished']:
                j['_independent_recovery']=p.name;return True
        return False
    p,j=latest('fixed_minimum_frequency_*.json')
    if restored(j) and j['retest'].get('status'):
        add(['O-PARAM-008'],'参数表/网关子范围通过','表下限/默认/上限0/5/30Hz；0、5、30经330网关写入316且稳定回读。未清EEPROM，不代表首次默认或端子频率验收。',p)
    p,j=latest('fixed_emergency_defrost_*.json')
    if restored(j) and j['retest'].get('status'):
        e=j['retest'];add(['O-DEFROST-020','T16-005'],'急停中止子范围通过',f'内机正常启机制热、HMI请求建立化霜8后触发消防急停；约{e["clear_after_s"]:.3f}秒观察到负载、阶段、内部状态和330占用全清，包含输入确认及通讯延迟。解除急停并复位、保持原制热选择，5秒内未续跑旧化霜。非端子或完整重新启机验收。',p)
    p,j=latest('fixed_fan_minimum_stop_*.json')
    if restored(j):
        for r in j['retest']['pairs']:
            ok=bool(r.get('status'))
            detail=(f'直接模拟316需求输入，配对{r["unit_type"]}/{r["fan_type"]}；'+
                    (f'同路风机实际停机{r["restart_off_seconds"]}秒后重启。' if ok else '轮换到另一台风机，未取得同路重启证据，测试条件不足，不能判固件失败。')+
                    '内机保持停机，此证据只属外机单独复测，不算内机到外机联合链通过。')
            add(r['ids'],'外机单独输入子范围通过' if ok else '同路重启证据不足；联合复测中',detail,p)
    p,j=latest('fixed_timed_defrost15_*.json')
    if j:
        e=j['retest']
        if restored(j) and e.get('status'):
            detail=e['status']+'；从内机正常启机；正常探头化霜、4～6℃时长及正式恢复时序另验。'
            if j.get('_independent_recovery'):detail+='收尾脚本缺少函数导入而中断，原异常保留；独立恢复及随后全通过审计已完成，见'+j['_independent_recovery']+'。'
            add(e['ids'],'故障定时化霜子范围通过',detail,p)
        else:
            d=e.get('diagnostics',[]);last=d[-1] if d else None
            detail='从内机正常启机，经正常通讯形成外机需求；真实累计20分钟间隔。'
            if last:detail+=f'最近{last["at"]}，环温{last["params"]["1422"]/10}℃，健康系统间隔计数{last["DefGapCount"][1]}秒。'
            if e.get('error'):detail+='本批异常已留证，结论待核；'+e['error'].splitlines()[-1][:180]
            lines.append((e['ids'],'运行中' if not e.get('finished') else '未完成；原因待核',detail,p))
    p,j=latest('outdoor24_settled_parameter_boundaries_*.json')
    if not restored(j):p,j=latest('outdoor24_gateway_parameter_boundaries_*.json')
    if restored(j):
        for r in j['parameter_matrix']['cases']:
            if 'software_scope_passed' not in r:continue
            low,high=r['expected'][1:];effective=r['table_matches_spec']
            for point in r['points']:
                stable=[s for s in point['samples'] if s['elapsed']>=2]
                effective=effective and bool(stable) and all(
                    (s['destination']==point['requested'] and (r['shared_source'] is None or s['source']==point['requested']))
                    if point['legal'] else low<=s['destination']<=high for s in stable)
            status=('默认表/边界写入子范围通过' if r['software_scope_passed'] else
                    '生效值/范围子范围通过；镜像窗口另验' if effective else '参数边界观察待分析')
            add([r['id']],status,
                f'316[{r["parameter"]}]初始化表{r["initialized_table"]}；合法上下限/默认及上下界外一单位经330正常协议写入，覆盖共享源；'+('每点等待实际值与镜像传播到位后连续稳定3秒。' if j['parameter_matrix'].get('wait_for_full_propagation') else '每点仅4秒窗口，部分值尚在传播，不作为固件失败；待传播到位复测。')+'逐点结果见原始记录。未验证首次EEPROM默认和运行算法。',p)
    p,j=latest('indoor_driven_six_fan_pairs_*.json')
    if restored(j):
        for r in j['joint_fans']['pairs']:
            if not r.get('status'):continue
            add(r['ids'],'内机正常启停风机子范围通过',
                f'配对{r["unit_type"]}/{r["fan_type"]}，仅通过330[398]正常启停，未直接写316需求；NTC0输入26℃。同路风机遵守90秒设定，观测停机秒数{r["restart_off_seconds"]}。BENCH软件边沿，正式档/物理端子及其它曲线另验。',p)
    for pattern,ids in [('T10-018_T10-019_allocation_*.json',['T10-018','T10-019']),
                        ('T12-005_refrigerant_bridge_*.json',['T12-005']),
                        ('T06-024_DA8_manual_characterization_*.json',['T06-024'])]:
        p,j=latest(pattern)
        if restored(j) and j['priority_case'].get('status')!='running' and not j['priority_case'].get('execution_error'):
            add(ids,'新版已复测；保留原子范围限制',j['priority_case']['status'],p)
    p,j=latest('outdoor_NTC_protection_recovery_*.json')
    if restored(j):
        for r in j['continuation_case']['cases']:
            if 'alarm_auto_cleared_without_reset' in r:
                add([r['id']],r['status'],f'原始NTC{r["channel"]}输入异常后对应系统保护，撤源后自动清警；330镜像出现{r["330_fault_mirror"]}、解除{r["recovered_330_mirror"]}。正常内机需求；真实断线及其它组合另验。',p)
    p,j=latest('O-HEATFAN-002_two_fixed_hysteresis_*.json')
    if restored(j) and j['continuation_case'].get('status')=='completed_boundaries_2compressor_subscope':
        add(['O-HEATFAN-002'],'双压机制热风机回差子范围通过','内机正常制热；环温6.9/7/9/12/12.1/10/6.9℃，各点精确输入保持33秒，风机数量2/2/2/2/1/1/2。其它配对、轮换和正式档/端子另验。',p)
    p,j=latest('outdoor_NTC_mirror_streaming_recheck_*.json')
    if restored(j):
        for r in j['mirror_recheck']['cases']:
            if not r.get('finished'):continue
            add([r['id']],r['status'],
                f'原始NTC{r["channel"]}输入异常，持续同步采集316告警/输出与330镜像；镜像置位观察={r["mirror_assert_seen"]}，保持期源告警掉落样本={r["source_alarm_dropout_count"]}；撤源后告警及镜像自动清除。软件输入范围，真实断线和端子另验。',p)
    for p in sorted(DAY.glob('outdoor_running_disable_*.json')):
        try:j=json.loads(p.read_text('utf8'))
        except (OSError,ValueError):continue
        if not restored(j):continue
        e=j.get('continuation_case',{})
        if e.get('status')!='completed_automatic_current_pair_only':continue
        for cid in sorted({r['id'] for r in e['cases']}):
            add([cid],'运行中禁用软件子范围通过',
                f'机型/风机配对{e["type_pair"]}；内机正常启机，分别禁用两压机、同时禁用及整机禁用，健康另一外机继续制热；解除禁用后按正常调度恢复。其它模式、化霜中禁用及端子另验。',p)
    p,j=latest('T15-009_coil_continuity_*.json')
    if restored(j) and j['priority_case'].get('finished') and not j['priority_case'].get('execution_error'):
        add(['T15-009'],'回路1连续性软件子范围通过',j['priority_case']['status']+'；其它回路、物理输入和正式档另验。',p)
    p,j=latest('four_coil_real_300_120_*.json')
    if restored(j):
        for i in range(4):
            cid=f'T15-{i+1:03d}';e=j.get('cases',{}).get(cid,{})
            if e.get('passed'):
                add([cid],'四盘管300/120秒软件子范围通过',f'已安装回路{i+1}低温保护约{e["trip_times"][str(i)]["elapsed_s"]:.3f}秒置位，解禁约{e["release_times"][str(i)]["elapsed_s"]:.3f}秒解除；原始ADC输入，未写计数/状态；BENCH软件观测、非物理端子/正式档验收。',p)
    for name,key,count in [('室外机逐项测试表_20261110.csv.txt','用例',156),('内机剩余150项明日安排_20261110.csv.txt','原用例',150)]:
        table=ROOT/name;rows=list(csv.DictReader(io.StringIO(table.read_text('utf-8-sig'))));assert len(rows)==count
        fields=list(rows[0]);extra=['V10.56_V12.40状态','V10.56_V12.40证据','V10.56_V12.40覆盖范围']
        for f in extra:
            if f not in fields:fields.append(f)
        for row in rows:
            for f in extra:row.setdefault(f,'')
            if row[key] in updates:
                u=updates[row[key]];row.update(zip(extra,[u['status'],u['path'].relative_to(ROOT).as_posix(),u['detail']]))
        buf=io.StringIO(newline='');w=csv.DictWriter(buf,fieldnames=fields);w.writeheader();w.writerows(rows);table.write_text(buf.getvalue(),encoding='utf8')
    body=['# 修复后内外机联合实测（2026-11-10）','',
          '板上330 V10.56 / 两块316 V12.40，BENCH_ONLY_3S。三板烧录逐字节核验及独立版本/配置审计已记录；此后测试不改固件。软件输出不是物理端子测量，BENCH不代替正式档时序。','',
          '用户指出内机停机而外机响应：首轮风机复测直接模拟了316需求输入，属于外机单独测试。13:36:49只读核对三板请求、负载和化霜阶段均已归零。后续联合启停从330正常启机入口执行，不用直接写外机需求代替联合链。','',
          '历史失败与旧版本结果保留；两份执行表另加新版状态/证据/覆盖范围三列。下表列子范围，不能据行数称全部验收完成。','',
          '|用例|结果|覆盖范围与限制|证据|','|---|---|---|---|']
    for ids,status,detail,p in lines:body.append(f'|{", ".join(ids)}|{status}|{detail}|[{p.stem}]({p.relative_to(ROOT).as_posix()})|')
    for old in sorted(DAY.glob('fixed_timed_defrost15_*.json')):
        try:z=json.loads(old.read_text('utf8'))
        except (ValueError,OSError):continue
        if 'unexpected temperature hold' not in z.get('retest',{}).get('error',''):continue
        ee=z['retest'];cross=ee['input_events'][-1]['t']
        first=next((r for r in ee['diagnostics'] if r['t']>=cross and r['params']['1421'] in (1,5,8)),None)
        if first:
            body+=['',f'首轮定时测试记录：16→12℃后约{first["t"]-cross:.3f}秒已经请求化霜，但脚本重复检查首次请求的20秒上限，误将等待330许可的时间也纳入该断言而退出。首轮正常停机观察曾超时，基础恢复随后完成，14:02:18独立审计全部通过；该轮不用于判定完整化霜时长。[原始异常]({old.relative_to(ROOT).as_posix()})。']
    p,j=latest('continuation_queue_*.json')
    if j:
        body+=['',f'续测队列：{j["status"]}；已开始批次：'+', '.join(r['action'] for r in j['runs'])+f'。记录[{p.stem}]({p.relative_to(ROOT).as_posix()})。']
    p,j=latest('settled_parameter_followup_*.json')
    if j:
        body+=['',f'参数传播到位补测：{j["status"]}。记录[{p.stem}]({p.relative_to(ROOT).as_posix()})。']
    p,j=latest('final_independent_readback_*.json')
    if j:body+=['',f'最近独立收尾：{j["started"]}，通过={j["passed"]}。仅代表该时点；后续运行需重新收尾。[证据]({p.relative_to(ROOT).as_posix()})。']
    body+=['','仍需分别保留：仪表/端子、真实断电保存、真实分路断线重连、正式档时序、3/4台及5～8回路硬件、暂缓通风及连续2小时等缺口。无法取得条件的项目不计通过，继续其它可测项。','',
           '更新时间：'+datetime.datetime.now().astimezone().isoformat(timespec='seconds')]
    (ROOT/'修复后内外机联合实测_20261110.md').write_text('\n'.join(body)+'\n',encoding='utf8')
    (DAY/'current_image_scope_summary.json').write_text(json.dumps({cid:dict(status=u['status'],detail=u['detail'],path=u['path'].relative_to(ROOT).as_posix()) for cid,u in updates.items()},ensure_ascii=False,indent=2),encoding='utf8')
    print('Published current-image scopes',len(updates))

if __name__=='__main__':main()
