"""Render only saved evidence for the Nov17 V12.46 fix and retest."""
import hashlib
import json
import shutil
import zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/单变频降载修复_20261117/最低频默认30Hz_V12.46'
B=R/'.codex-tmp/vfd_unload_min30_v1063_v1246_20261117'
RELEASE=R/'固件_330V10.63_316V12.46_单变频降载修复_20261117'


def read(p):return json.loads(p.read_text('utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def link(p):return p.relative_to(R).as_posix()


def main():
    RELEASE.mkdir(exist_ok=True)
    result=dict(generated=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
                indoor_version='10.63',outdoor_version='12.46',profiles={},curves=[],automatic=[])
    lines=['# 单变频降载修复与复测（2026-11-17）','',
        '外机V12.46修复Ⅱ型、Ⅲ型单变频在非秒节拍扫描时提前停风机。先判断频率是否高于最低值，再由1秒节拍执行降频；只有到最低值后，才进入既有最小运行时间和动作间隔判断。',
        '按用户当日最新要求，最低频率默认改为30Hz、可设0～30Hz；最高频率默认50Hz、可设30～50Hz。0～50Hz固定对应0～10V（30Hz=6V，40Hz=8V，50Hz=10V）。已有合法保存值保留，默认值不等于覆盖现场设定。','',
        '固件改动仅涉及316的UserAction.c、user.c及User.h；330仍为V10.63。未改变寄存器地址、调速设定、温度边界、保护逻辑或正式／BENCH时序定义。','']
    baseline=read(R/'.codex-tmp/manual_gate_v1063_v1244_20261113/BENCH_ONLY_3S/manifest.json')
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        m=read(B/profile/'manifest.json')
        mismatch=[n for n,h in m['source_inventory'].items() if sha(R/n)!=h]
        artifact_mismatch=[n for n,h in m['artifacts'].items() if sha(B/profile/n)!=h]
        assert not mismatch and not artifact_mismatch
        changed=[n for n,h in baseline['source_inventory'].items() if m['source_inventory'][n]!=h]
        assert len(changed)==3
        folder=RELEASE/profile;folder.mkdir(exist_ok=True)
        for name in m['artifacts']:shutil.copy2(B/profile/name,folder/name)
        shutil.copy2(B/profile/'manifest.json',folder/'manifest.json')
        shutil.copy2(B/profile/'build316.log',folder/'build316.log')
        result['profiles'][profile]=dict(source_entries=len(m['source_inventory']),changed_from_v1244=changed,
            source_mismatches=mismatch,artifact_mismatches=artifact_mismatch,artifacts=m['artifacts'])
        lines+=[f'- {profile}：编译0错误、0警告；{len(m["source_inventory"])}条源码和全部产物哈希匹配。']
    lines+=['','修改定位：[降载分支](PSC316RK-V12-外机/WELLTHINKER/User/UserAction.c#L1459)、[参数默认值](PSC316RK-V12-外机/WELLTHINKER/User/user.c#L316)。','']
    arm=read(B/'unload_ARM_regression.json');interlocks=read(B/'ARM_regression.json')
    result['arm']=arm;result['interlocks_arm']=interlocks
    assert all(r['passed'] for r in arm['results']+interlocks['results'])
    ramp_count=sum(len(r['ramps'])+len(r['default30_ramps']) for r in arm['results'])
    compare_count=sum(r['unchanged_fan_branch_comparisons'] for r in arm['results'])
    lines+=[f'实际编译ARM离线验证：两档共{ramp_count}组降载到10Hz／30Hz并停机的过程，插入非秒节拍扫描；{compare_count}组其他风机分支与旧版一致。最小运行、最小停机及动作间隔门槛通过。两档各501个0.1Hz步进点的AO换算通过；默认表及已有设定保留检查通过。',
        '自动输出比较'+str(sum(r['automatic_old_new_equal'] for r in interlocks['results']))+'组一致，手动风机联锁'+str(sum(r['manual_fan_cases'] for r in interlocks['results']))+'组、故障／禁用／急停'+str(sum(r['fault_disable_emergency_cases'] for r in interlocks['results']))+'组通过。上述为ARM函数执行，不等同整板或正式时序验收。','']
    for name in ('unload_ARM_regression.json','ARM_regression.json'):
        shutil.copy2(B/name,RELEASE/name)
    deployment=D/'deployment.json'
    if deployment.exists():
        q=read(deployment);result['deployment']=dict(verified=q.get('verified',False),boards=q.get('boards'),
            versions_after=q.get('versions_after'),configuration_changes=q.get('configuration_changes'),evidence=link(deployment))
        lines+=['本次烧录：验证完成='+str(q.get('verified',False))+'；两块316完整HEX回读，330只核验原镜像。[记录]('+link(deployment)+')。','']
    lines+=['|板上批次|全部判据|参数及输入恢复|加载／降载速度|证据|','|---|---|---|---|---|']
    for p in sorted(D.glob('targeted_vfd_*.json')):
        q=read(p)
        row=dict(pair=q['pair'],minimum30_only=q.get('minimum30_only',False),checks=q['checks'],passed=q.get('passed',False),restored=q.get('restored',False),
            ai_restore_verified=q.get('ai_restore_verified',False),load_rates=q.get('measured_load_rates_Hz_per_s'),
            unload_rates=q.get('measured_unload_rates_Hz_per_s'),off_edges=q.get('off_edges'),
            minimum30_unload_rate=q.get('minimum30_unload_rate_Hz_per_s'),minimum30_off_edges=q.get('minimum30_off_edges'),
            default_tables_on_board=q.get('default_tables_on_board'),driver_sha256=q.get('driver_sha256'),
            error=q.get('error'),evidence=link(p))
        # A later optional30Hz exchange failed after the primary10Hz curve
        # completed. Derive the primary evidence separately, never rewrite it.
        if q.get('error') and q['points'][-1]['label']=='minimum30_unload33C_to_off' and not q['points'][-1]['samples']:
            primary=[point for point in q['points'] if point['label']=='unload33C_to_fans_off']
            if len(primary)==1:
                samples=primary[0]['samples'];steps=[]
                for a,z in zip(samples,samples[1:]):
                    delta=a['OutdoorVfdSpeed']-z['OutdoorVfdSpeed']
                    if delta>0 and a['OutdoorVfdOn'] and z['OutdoorVfdOn']:
                        steps.append(dict(t=z['t'],delta10=delta))
                rate=sum(e['delta10'] for e in steps[1:])/10/(steps[-1]['t']-steps[0]['t']) if len(steps)>=5 else None
                required=('minimum_frequency','maximum40_reached','normal_load_step_1Hz','load_rate_1.0Hz_per_s',
                    'hold_35C','maximum30_software6V','intermediate_hold_35C','primary_unload_from40_established',
                    'unload_to_off','unload_reaches_minimum_before_off')
                checks={key:q['checks'].get(key,False) for key in required}
                checks['unload_rate_and_steps']=rate is not None and abs(rate-1)<=.15 and all(e['delta10']==10 for e in steps)
                primary_samples=[s for point in q['points'][:q['points'].index(primary[0])+1] for s in point['samples']]
                checks['bounds']=all(s['OutdoorVfdSpeed']==0 or 100<=s['OutdoorVfdSpeed']<=400 for s in primary_samples)
                stable=[z for a,z in zip(primary_samples,primary_samples[1:]) if a['OutdoorVfdSpeed']==z['OutdoorVfdSpeed']]
                checks['AO_ratio']=bool(stable) and all(s['ao']==2*s['OutdoorVfdSpeed'] for s in stable)
                row['primary_analysis']=dict(source_sha256=sha(p),checks=checks,passed=all(checks.values()),unload_rate=rate,
                    note='Primary10Hz evidence complete; optional30Hz input switch failed on a serial read. Original batch error retained.')
                analysis=D/'derived_primary_analysis';analysis.mkdir(exist_ok=True)
                (analysis/p.name).write_text(json.dumps(row['primary_analysis'],ensure_ascii=False,indent=2),encoding='utf8')
        result['curves'].append(row)
        name={(1,2):'Ⅱ型单变频',(2,2):'Ⅲ型单变频',(2,4):'Ⅲ型一定一变'}[tuple(q['pair'])]
        if row['minimum30_only']:name+='（30Hz独立补测）'
        lines.append(f'|{name}|{row["passed"]}|{row["restored"] and row["ai_restore_verified"]}|{row["load_rates"]}／{row["unload_rates"]}|[记录]({link(p)})|')
    lines+=['','单变频两批先保留10Hz测试下限，以复测原40Hz／30Hz直接关闭的缺陷。Ⅲ型另加30Hz下限的板上运行、加载和降载验证。软件AO来自316实际运行回读；采样跨1Hz边沿时，停机前最后运行采样允许为11Hz／31Hz，不把它解释为持续最低频率驻留测量。','']
    for row in result['curves']:
        lines+=['- 配置'+str(row['pair'])+'：'+json.dumps(row['checks'],ensure_ascii=False)]
        if row['default_tables_on_board']:
            lines.append('  - 板上默认表读回：'+json.dumps(row['default_tables_on_board'],ensure_ascii=False)+'。')
        for e in (row['off_edges'] or []):
            lines.append(f'  - 停机前最后采样{e["previous_speed10"]/10:.1f}Hz、软件AO={e["previous_ao"]}，时间{e["at"]}。')
        if row['minimum30_unload_rate'] is not None:
            lines.append(f'  - 30Hz下限另测降载速度约{row["minimum30_unload_rate"]:.3f}Hz/s；停机边沿{row["minimum30_off_edges"]}。')
        if row.get('primary_analysis'):
            lines.append('  - 本批主曲线独立复核通过='+str(row['primary_analysis']['passed'])+'，降载约'+str(round(row['primary_analysis']['unload_rate'],3))+'Hz/s；随后30Hz补测的输入切换遇一次Modbus无应答，原始整批错误保留，后续30Hz独立补测另列。')
    lines.append('')
    for p in sorted(D.glob('rerun_fan_interlock_and_automatic_regression_*.json')):
        q=read(p);e=q['manual_automatic_regression']
        result['automatic'].append(dict(passed=e.get('passed',False),restored=q.get('restored',False),
            checks=e.get('checks'),fan_lead=e.get('automatic_fan_lead'),error=e.get('error'),evidence=link(p)))
        lines+=['整板自动／手动联锁回归：通过='+str(e.get('passed',False))+'，恢复='+str(q.get('restored',False))+'。[记录]('+link(p)+')。','']
    audits=[]
    for p in list(D.glob('*audit*.json'))+list(D.glob('after_*.json'))+list(D.glob('post_flash*.json')):
        q=read(p)
        if q.get('verified'):audits.append((p,q))
    if audits:
        p,q=max(audits,key=lambda v:v[0].stat().st_mtime)
        result['latest_audit']=dict(verified=True,evidence=link(p),at=q.get('finished'))
        lines+=['最近独立审计通过：版本、整幅固件回读、已恢复参数和所有负载停止状态。[记录]('+link(p)+')。','']
    lines+=['本轮上板为BENCH_ONLY_3S测试档。正式档完成编译及ARM回归，正式28项时序、2小时稳定性、物理0～10V端子量测仍按此前要求保留。本报告不替代这些验收，也不关闭AI输入条件不足等历史待测项。',
        '前一中间版本V12.45烧录后的首次比较遇到330 AI校准镜像尚未回填，原始失败记录保留；等待正常轮询后重复读回793项一致、独立审计通过。本次V12.46烧录明确等待回填后核验，不将该测试取样时机问题计作固件缺陷。','',
        '[完整连续记录]('+link(D/'events.jsonl')+')；[固件目录]('+link(RELEASE)+')。']
    covered={tuple(r['pair']) for r in result['curves'] if not r['minimum30_only'] and
             (r['passed'] or r.get('primary_analysis',{}).get('passed')) and r['restored'] and r['ai_restore_verified']}
    result['all_three_curve_pairs_passed']=covered=={(1,2),(2,2),(2,4)}
    result['minimum30_board_supplement_passed']=any(r['minimum30_only'] and r['passed'] and r['restored'] and r['ai_restore_verified'] for r in result['curves'])
    result['automatic_board_regression_passed']=bool(result['automatic']) and all(r['passed'] and r['restored'] for r in result['automatic'])
    (D/'fix_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    (RELEASE/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    report=R/'单变频降载修复与复测_20261117.md';report.write_text('\n'.join(lines)+'\n',encoding='utf8')
    shutil.copy2(report,RELEASE/report.name)
    for name in result['profiles']['BENCH_ONLY_3S']['changed_from_v1244']:
        dest=RELEASE/'修改源码'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/name,dest)
    for name in ('build_vfd_unload_v1245_20261117.py','build_vfd_min30_v1246_20261117.py',
        'test_vfd_unload_v1246_arm.py','test_vfd_unload_interlocks_v1246_arm.py','vfd_min30_fix_context_20261117.py',
        'deploy_vfd_min30_v1246_20261117.py','retest_vfd_unload_v1246_20261117.py',Path(__file__).name):
        dest=RELEASE/'验证脚本'/name;dest.parent.mkdir(exist_ok=True);shutil.copy2(R/'tools'/name,dest)
    inventory={p.relative_to(D).as_posix():sha(p) for p in D.rglob('*') if p.is_file() and p.name!='evidence_inventory.json'}
    (D/'evidence_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf8')
    hashes={p.relative_to(RELEASE).as_posix():sha(p) for p in RELEASE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
    (RELEASE/'SHA256.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf8')
    if result['all_three_curve_pairs_passed'] and result['minimum30_board_supplement_passed'] and result['automatic_board_regression_passed']:
        with zipfile.ZipFile(RELEASE.with_name(RELEASE.name+'.zip'),'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for p in RELEASE.rglob('*'):
                if p.is_file():archive.write(p,p.relative_to(RELEASE.parent))
    print('REPORT UPDATED','curves_passed',result['all_three_curve_pairs_passed'],'automatic',result['automatic_board_regression_passed'],flush=True)


if __name__=='__main__':main()
