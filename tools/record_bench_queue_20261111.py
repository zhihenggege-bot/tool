"""Publish only observed board-test scopes to the original 2026-11-11 queue."""
import csv
import json
import time
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DAY=ROOT/'测试证据/台架执行_20261111'
QUEUE=ROOT/'内外机台架测试队列_20261111.csv.txt'


def record(path, entries):
    with QUEUE.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f); fields=reader.fieldnames; rows=list(reader)
    by_id={r['用例']:r for r in rows}
    assert len(rows)==len(by_id)==306
    for cid,status,result,recovery in entries:
        row=by_id[cid]; evidence=path.relative_to(ROOT).as_posix()
        if row['新证据'] and evidence not in row['新证据'].split('；'):
            evidence=row['新证据']+'；'+evidence
        row.update({'执行状态':status,'结果':result,'新证据':evidence,'恢复核验':recovery})
    temp=QUEUE.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    temp.replace(QUEUE)


def publish():
    for path in sorted(DAY.glob('B01_NTC_*.json')):
        d=json.loads(path.read_text('utf8')); batch=d['B01']; entries=[]
        for row in batch['cases']:
            if 'finished' not in row: continue
            yes=lambda key:'有' if row.get(key) else '未见'
            if row.get('stimulus_requested'):
                result=(f'1# NTC{row["channel"]}采集层模拟；316[{row["alarm"]}]；预期压机动作{yes("protection_seen")}，'
                        f'2#持续制热{yes("peer_continues")}；330逐条镜像{yes("mirror_seen")}，'
                        f'实时保护一致{yes("layer_seen")}，历史字有保护记录{yes("latch_seen")}；'
                        f'轮次变化{row.get("poll_round_changes",0)}次，保护连续掉落样本{row.get("source_dropout","未测得")}。')
            else: result='本轮未建立用例输入前置；未施加该路模拟。'
            if row.get('hold_window_timeout'): result+=f'{batch.get("hold_limit_s",60)}秒观察窗未覆盖三次完整故障轮询。'
            if row.get('error'): result+=' 采集记录：'+row['error']
            entries.append((row['id'],row['status'],result,
                            '撤源后本机与330实时故障清除' if row['recovery_verified'] else '本例恢复未核验'))
        if entries: record(path,entries)
    for path in sorted(DAY.glob('B02_parameters_*.json')):
        d=json.loads(path.read_text('utf8')); entries=[]
        for row in d['cases']:
            if 'finished' not in row: continue
            p=row['parameter']
            route={193:'两台实值与330镜像均跟随330[41]；写逐台193后最终回到全局源。',
                   176:'1319=1时逐台写拒绝并返回诊断9；共享源1340更新两台；1319=0只更新1#。',
                   165:'停机时两台由0/1改成非法1/1，保护字bit6置位、输出保持关闭；恢复0/1后实时保护解除。其它非法组合与运行需求另验。'}[p]
            result=f'316[{p}] 写入目标{row["request"]}；'+(route if row['status']=='软件子范围通过' else row.get('error','结果见原始证据'))
            entries.append((row['id'],row['status'],result,'两台实值、镜像、共享源和开关恢复' if row['recovery_verified'] else '恢复未核验'))
        if entries: record(path,entries)
    for path in sorted(DAY.glob('B01_contacts_*.json')):
        d=json.loads(path.read_text('utf8')); entries=[]
        groups={}
        for row in d['B01_contacts']['cases']:
            if 'finished' in row: groups.setdefault(row['id'],[]).append(row)
        for cid,rows in groups.items():
            manual=d['B01_contacts'].get('manual',False)
            status='软件子范围通过' if len(rows)==(4 if manual else 2) and all(r['status']=='软件子范围通过' for r in rows) else '实测有待核对'
            notes=[]
            for r in rows:
                action='保护动作已见' if r.get('protection_seen') else '保护动作未核到'
                mirror='逐条镜像已见' if r.get('mirror_seen') else '逐条镜像未核到'
                notes.append(f'X{r["ch"]:02d}：{action}，{mirror}'+('，'+r['error'] if r.get('error') else ''))
                if r.get('source_dropout_samples'):notes[-1]+=f'，源输入掉落{r["source_dropout_samples"]}样本（连续时序不判通过）'
                if r.get('held_page_isolation'):notes[-1]+='，切换另一台页面对照='+str(r['held_page_isolation'])
            entries.append((cid,status,('1# 手动命令持续开启时HP/LP/过载/风机极性模拟；环温故障子范围另验；' if manual else '1# 极性输入模拟；')+'；'.join(notes),
                            '模拟撤除、极性回读和实时故障恢复' if all(r['recovery_verified'] for r in rows) else '部分触点恢复未核验'))
        if entries: record(path,entries)
    pressure_fan={}
    for path in sorted(DAY.glob('B03_pressure_fan_*.json'),key=lambda p:p.stat().st_mtime):
        d=json.loads(path.read_text('utf8')); e=d['fixed_vfd']; points=[p for p in e['points'] if 'final' in p]
        if not e.get('finished') or not points:continue
        ids=e['ids']; entries=[]; pair='/'.join(map(str,e['pair']))
        rows={p['label']:p for p in points}
        pressure_fan[pair]=path
        for cid in ids:
            if e['pair'][1]==3:
                names={'O-FANCURVE-005':('TL','TL_plus_half','TL_plus_TLD','above_TL_plus_TLD'),
                       'O-FANCURVE-006':('lower_temp_selects_stage',),'O-FANCURVE-007':('force_at_50',)}[cid]
                selected=[rows[n] for n in names if n in rows]
                info='；'.join(f'{r["label"]}实测段{r["final"].get("OutdoorFanStage")}，预期段{r.get("expected_stage")}' for r in selected)
                good=bool(selected) and len(selected)==len(names) and all(r['behavior_matches'] for r in selected)
            else:
                names={
                    'O-FANCURVE-012':('34C_both_hold_boundary','36C_both_hold_boundary','37C_full_load_switch_and_rate','33C_unload_switch_to_fans_off'),
                    'O-FANCURVE-013':('37C_establish_full_load','33C_unload_switch_to_fans_off'),
                    'O-FANCURVE-014':('37C_full_load_switch_and_rate',),
                    'O-FANCURVE-015':('45_1C_after_verified_off',),
                    'O-FANCURVE-016':('36C_both_hold_boundary','35C_36C_hold_boundary'),
                    'O-FANCURVE-017':('37C_full_load_switch_and_rate',),
                    'O-FANCURVE-018':('33C_unload_switch_to_fans_off',),
                    'O-FANCURVE-019':('37C_full_load_switch_and_rate','45_1C_after_verified_off'),
                    'O-FANCURVE-020':('35C_intermediate_hold','37C_full_load_switch_and_rate'),
                }[cid]
                selected=[rows[n] for n in names if n in rows]
                info='；'.join(f'{r["label"]}：{r["first_speed10"]/10:g}→{r["last_speed10"]/10:g}Hz，DA0={r["final"]["ao"]}' for r in selected)
                good=cid=='O-FANCURVE-016' and e.get('intermediate_established') and len(selected)==len(names) and all(r['behavior_matches'] for r in selected)
            if not selected:continue
            recovery='本例压力输入跨度和本机参数已回读恢复' if d.get('restored') and e.get('ai_restore_verified') and all(e['ai_restore_verified'].values()) else '本例完整恢复需看独立回读'
            entries.append((cid,'软件子范围通过' if good else '已有本轮板测轨迹',f'外机配置{pair}；{info}；物理端子与正式时序另验。',recovery))
        if entries:record(path,entries)
    publish_additional()
    publish_progress()


def publish_progress():
    with QUEUE.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    counts={unit:dict(Counter(r['执行状态'] for r in rows if r['机组']==unit)) for unit in ('330','316')}
    controller=max(DAY.glob('pending_controller_*.json'),key=lambda p:p.stat().st_mtime)
    controller_data=json.loads(controller.read_text('utf8'))
    progress=dict(at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),status='continuous_queue_in_progress',
        controller=controller.relative_to(ROOT).as_posix(),controller_status=controller_data.get('status'),
        counts=counts,pending=sum(r['执行状态']=='待执行' for r in rows),
        complete_acceptance_claimed=False,firmware_changed=False)
    (DAY/'live_progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# 内外机连续测试实时进度','',f'更新时间：{progress["at"]}。队列仍在执行；固件未修改、未烧录。','',
        '|机组|状态|项目数|','|---|---|---:|']
    for unit,states in counts.items():
        lines.extend(f'|{unit}|{state}|{count}|' for state,count in states.items())
    lines+=['',f'当前待执行 {progress["pending"]} 项。软件子范围通过不等于整项验收完成。',
        '', '按单写入进程连续执行；普通差异留证，撤源、参数恢复和三板独立核验后继续。',
        '', '[逐项队列](内外机台架测试队列_20261111.csv.txt)；[控制器记录]('+progress['controller']+')。',
        '', '运行中的用例不能视为已恢复；最终收尾以本轮末尾独立核验为准。']
    (ROOT/'台架连续测试进度_20261111.md').write_text('\n'.join(lines)+'\n',encoding='utf8')


def publish_additional():
    """Retain observed subscopes; no inference of complete acceptance."""
    functional_scopes={}
    for path in sorted(DAY.glob('*.json'),key=lambda p:p.stat().st_mtime):
        try:d=json.loads(path.read_text('utf8'))
        except (ValueError,OSError):continue
        if not isinstance(d,dict) or not d.get('restored'):continue
        recovery='本批正常停机、撤源及参数恢复；完整结果另见各批独立三板回读'
        entries=[]
        e=d.get('remaining_functional',{})
        if e.get('finished'):
            groups={}
            for r in e.get('cases',[])+e.get('events',[]):
                if 'final' in r or 'passed' in r:groups.setdefault(r['id'],[]).append(r)
            for cid,rs in groups.items():
                # An exception in prepare() can leave a pre-created row with
                # passed=False but no case observation or applied input. Keep
                # that ID pending; the batch error remains in the issue log.
                if e.get('error') and not any(r.get('samples') or 'final' in r for r in rs):continue
                all_known=all('passed' in r for r in rs)
                known_bad=any(r.get('passed') is False for r in rs)
                status='实测有待核对' if known_bad else '软件子范围通过' if all_known and not e.get('error') else '已有本轮板测轨迹'
                details='；'.join(r.get('label','')+('='+str(r.get('passed')) if 'passed' in r else '=仅观察')+
                    ('，'+r['error'] if r.get('error') else '')+('，范围：'+r['limit'] if r.get('limit') else '') for r in rs)
                functional_scopes[(cid,e['kind'])]=(path,cid,status,
                    f'{e["kind"]}，配置{e.get("pair", "见证据")}；{details}；'+e['scope'],recovery)
        e=d.get('parameter_matrix',{})
        if e.get('finished'):
            for r in e.get('cases',[]):
                default,low,high=r['expected']
                required=set((low,default,high,low-1,high+1))
                if {p['requested'] for p in r.get('points',[])}!=required or any('accepted_safely' not in p for p in r['points']):continue
                entries.append((r['id'],'软件子范围通过' if r.get('software_scope_passed') else '实测有待核对',
                    f'当前板上316[{r["parameter"]}]默认/上下限表{r["initialized_table"]}；正常330源的下限、默认、上限及上下越界写入均持续读回；软件范围匹配={r.get("software_scope_passed")}；首次EEPROM默认与物理输出另验。',recovery))
        if d.get('current_records'):
            for cid,r in d['current_records'].items():
                if cid=='T16-006':
                    entries.append(('O-DEFROST-010','软件子范围通过' if r['passed'] else '实测有待核对',
                        '当前版本真实化霜期间X00高压开关极性模拟：仅停压机1、不新增高压报警，撤源后本轮不重启；反方向X02及物理接点仍待验。',recovery))
                    continue
                if cid not in {f'T15-{i:03d}' for i in range(1,5)}:continue
                e=d.get('cases',{}).get(cid,{})
                entries.append((cid,'软件子范围通过' if r['passed'] else '实测有待核对',
                    '当前V10.58安装回路输入模拟；'+str(e.get('trip_times',{}))[:800]+'；恢复轨迹见证据；BENCH程序、物理端子另验。',recovery))
        if path.name.startswith('O-FANTIME_prestart_six_pairs'):
            e=d.get('priority_case',{})
            for r in e.get('pairs',[]):
                if not r.get('finished'):continue
                index=((0,0),(0,1),(1,2),(1,3),(2,2),(2,4)).index((r['unit_type'],r['fan_type']))
                entries.append((f'O-FANTIME-{1+index*4:03d}','实测有待核对' if r.get('violations') else '已有本轮板测轨迹',
                    '330停机下316正常请求输入子范围；'+r['status']+'；正式时序与330联合预启动另验。',recovery))
                if r.get('observed_minimum_runs'):
                    entries.append((f'O-FANTIME-{2+index*4:03d}','实测有待核对' if r.get('minimum_run_violations') else '软件子范围通过',
                        f'316正常请求输入后约11秒撤销；最低运行设置{r["minimum_run_s"]}秒，观测运行长度{r["observed_minimum_runs"]}；300秒运行与其它减载情形另验。',recovery))
                if 'conflicting_speed_samples' in r:
                    entries.append((f'O-FANTIME-{3+index*4:03d}','实测有待核对' if r['conflicting_speed_samples'] else '已有本轮板测轨迹',
                        f'本次启停轨迹双速互斥冲突样本{len(r["conflicting_speed_samples"])}；BENCH动作间隔为3秒，不替代正式15秒；主动反复升降档另验。',recovery))
        e=d.get('fan_curves',{})
        if e.get('finished'):
            labels={
                'O-FANCURVE-001':('condensing_equal45_no_raise','condensing_above45_5seconds','all_below30_full60seconds'),
                'O-FANCURVE-002':('ambient_equal25_no_raise','ambient_above25_full30seconds'),
                'O-FANCURVE-003':('system2_disabled_cold_ignored','system1_disabled_cold_ignored')}
            points={r['label']:r for r in e.get('points',[]) if 'final' in r}
            for cid,names in labels.items():
                rows=[points[n] for n in names if n in points]
                if not rows:continue
                ok=len(rows)==len(names) and all(r.get('passed') for r in rows)
                detail='；'.join(f'{r["label"]}末态{r["final_stage"]}' for r in rows)
                entries.append((cid,'软件子范围通过' if ok else '已有本轮板测轨迹',
                    f'配置{e["type_pair"]}；{detail}；未覆盖完整物理端子与正式时序。',recovery))
        e=d.get('continuation_case',{})
        if e.get('finished'):
            if 'type_pair' in e:
                for cid in set(r['id'] for r in e.get('cases',[])):
                    rows=[r for r in e['cases'] if r['id']==cid and r.get('observation')]
                    if rows:
                        entries.append((cid,'软件子范围通过' if all(r.get('status')=='软件自动运行子范围通过' for r in rows) else '已有本轮板测轨迹',
                            f'配置{e["type_pair"]}，正常330制热自动需求；'+ '；'.join(r['label'] for r in rows)+'；手动路径和化霜期间禁用另验。',recovery))
            elif e.get('id')=='O-HEATFAN-002':
                pts=[r for r in e.get('points',[]) if r.get('final')]
                if pts:entries.append((e['id'],'已有本轮板测轨迹',
                    '两定制热风机7/12℃回差；'+ '；'.join(f'{r["temp10"]/10:g}℃→{r["wanted_fans"]}台' for r in pts)+'；连续20分钟轮换与单压机范围另验。',recovery))
        e=d.get('priority_case',{})
        if e.get('finished'):
            for cid in e.get('ids',[]):
                if e.get('observations'):
                    entries.append((cid,'已有本轮板测轨迹',e.get('status','见原始轨迹')+'；手动指令建立化霜后施加消防输入；BENCH范围。',recovery))
            if path.name.startswith('T10-018_T10-019') and e.get('runs'):
                for cid in ('T10-018','T10-019'):
                    entries.append((cid,'已有本轮板测轨迹',e.get('status','范围未全部完成')+'；恢复阶段使用BENCH时长。',recovery))
            if path.name.startswith('T12-005') and e.get('runs'):
                entries.append(('T12-005','已有本轮板测轨迹',e.get('status','见冷媒桥接逐值记录'),recovery))
            if path.name.startswith('T06-024') and e.get('phases'):
                entries.append(('T06-024','已有本轮板测轨迹',e.get('status','见DA8逐段记录'),recovery))
            if path.name.startswith('T15-009') and e.get('samples'):
                entries.append(('T15-009','已有本轮板测轨迹',e.get('status','未完成全部连续性观察')+'；当前为回路1，未关闭其它已安装回路。',recovery))
        e=d.get('defrost_natural',{})
        if e.get('finished') and e.get('events'):
            events=e['events']
            for cid,key,note in (
                ('O-DEFROST-001','active_natural','自然15分钟间隔、正常输入建立化霜；逐个破坏7条件另验'),
                ('O-DEFROST-006','active_natural','一路满足入口时两压机进入；反向与未运行压机另验'),
                ('O-DEFROST-008','active_natural','化霜中风机/四通阀软件输出观察；实际端子另验'),
                ('O-DEFROST-009','second_fin_ends_defrost','两路翅温逐压机退出；40℃等号与反顺序另验'),
                ('O-DEFROST-013','both_clear_after_bench_recovery','BENCH恢复及Owner释放；正式60秒另验')):
                if key in events:entries.append((cid,'已有本轮板测轨迹',note,recovery))
        e=d.get('vent_ntc',{})
        for r in e.get('cases',[]):
            if not r.get('finished'):continue
            entries.append((r['id'],r.get('status','实测有待核对'),
                f'通风NTC{r["ch"]}原始输入{r["raw"]}，报警{r["alarm"]}，风机/冷热输出范围观察；'+r.get('error',''),
                '撤源/复位/风机状态核验通过' if r.get('recovery_verified') else '本例恢复未核验，见批次收尾'))
        e=d.get('cases',{}).get('T13-064',{})
        if e.get('passed'):
            entries.append(('T13-064','软件子范围通过',
                f'当前版本通风连续{e["elapsed_s"]:.1f}秒；20分钟/40分钟/60分钟三个连续读频段；真实端子与热工性能另验。',recovery))
        if entries:record(path,entries)
    for path in sorted(DAY.glob('B04_ambient_*.json')):
        d=json.loads(path.read_text('utf8')); e=d['ambient']; entries=[]; groups={}
        if not e.get('finished'):continue
        for row in e['points']:
            if 'final' in row:groups.setdefault(row['id'],[]).append(row)
        for cid,rows in groups.items():
            summary='；'.join(f'{r["label"]}：{r["temp10"]/10:g}℃，末态锁定={int(r["final"]["lock"])}' for r in rows)
            entries.append((cid,'已有本轮板测轨迹',summary+'；BENCH档，未关闭正式时间验收。','正常停机和参数回读' if d.get('restored') else '完整恢复需看独立回读'))
        if entries:record(path,entries)
    # A passing different subcase cannot erase an unresolved failed subcase
    # of the same queue ID. A later full retry of the same named scope replaces
    # that scope's result; all original evidence links remain in the ledger.
    by_id={}
    for entry in functional_scopes.values():by_id.setdefault(entry[1],[]).append(entry)
    for cid,scopes in by_id.items():
        statuses={r[2] for r in scopes}
        status=('实测有待核对' if '实测有待核对' in statuses else
                '已有本轮板测轨迹' if '已有本轮板测轨迹' in statuses else '软件子范围通过')
        result='；'.join(r[3] for r in scopes)
        for path,_,_,_,recovery in scopes:record(path,[(cid,status,result,recovery)])


if __name__=='__main__':
    publish()
    with QUEUE.open(encoding='utf-8-sig',newline='') as f:
        print(Counter((r['机组'],r['执行状态']) for r in csv.DictReader(f)))
