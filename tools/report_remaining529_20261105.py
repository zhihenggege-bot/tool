"""Merge explicit per-case offline evidence after all serial writers finish.

Never upgrades ARM/simulated-clock or Modbus evidence to physical acceptance.
Original board failures/history and all untouched unexecuted cases survive.
"""
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
from run_indoor_bench_20261105 import D,R,RESULTS,CASECSV,REPORT,now,dump

MATRICES=(
    'remaining529_offline_matrix.json','remaining529_pid_boundaries_ARM.json',
    'remaining529_protection_ARM.json','remaining529_outputs_ARM.json',
    'remaining529_allocation_edges_ARM.json','remaining529_special_abort_ARM.json',
    'remaining529_gates_ARM.json','remaining529_compatibility_ARM.json',
    'remaining529_lifecycle_configuration_ARM.json','remaining529_interactions_ARM.json',
    'remaining529_reverse_commands_ARM.json')


def main():
    rows=list(csv.DictReader(CASECSV.open(encoding='utf-8-sig',newline='')))
    fields=list(rows[0]);byid={r['用例编号']:r for r in rows}
    data=json.loads(RESULTS.read_text('utf8'))
    supplements=collections.defaultdict(list)
    checks_total=0
    for filename in MATRICES:
        p=D/filename
        report=json.loads(p.read_text('utf8'))
        assert not report.get('errors'),(filename,report.get('errors'))
        assert all(c['passed'] for c in report['checks']),filename
        checks_total+=len(report['checks'])
        for cid,checks in report['cases'].items():
            assert cid in byid,cid
            actual_checks=[c for c in checks if 'label' in c]
            assert actual_checks and all(c['passed'] for c in checks),(cid,filename)
            supplements[cid].append({'file':str(p.relative_to(R)).replace('\\','/'),
                'check_count':len(actual_checks),'hardware_access':False,'time_is_simulated':True,
                'first_check':actual_checks[0]['label'],'last_check':actual_checks[-1]['label']})
    # Explicit current-image transition evidence; no inference from a historical run.
    expanded=D/'expanded_ARM_matrix.json'
    x=json.loads(expanded.read_text('utf8'))
    assert x['passed']
    checks_total+=len(x['checks'])
    serial=11
    for source in range(6):
        for target in range(6):
            if source==target:continue
            selected=[c for c in x['checks'] if f'complete shutdown then transition {source}->{target}' in c['label']]
            assert len(selected)==2 and all(c['passed'] for c in selected)
            supplements[f'T13-{serial:03d}'].append({'file':str(expanded.relative_to(R)).replace('\\','/'),
                'check_count':len(selected),'hardware_access':False,'time_is_simulated':True,
                'first_check':selected[0]['label'],'last_check':selected[-1]['label']})
            serial+=1
    for cid,text in [('T13-043','combined zero stage 1/0'),('T13-044','combined zero stage 0/1'),
                     ('T13-046','exact999min exits running phase'),('T07-014','writable bounds register330')]:
        selected=[c for c in x['checks'] if text in c['label']]
        assert selected and all(c['passed'] for c in selected)
        supplements[cid].append({'file':str(expanded.relative_to(R)).replace('\\','/'),
            'check_count':len(selected),'hardware_access':False,'time_is_simulated':True,
            'first_check':selected[0]['label'],'last_check':selected[-1]['label']})
    additions=0
    for cid,evidence in supplements.items():
        if cid in data:
            data[cid]['offline_supplements']=evidence
            continue
        additions+=1
        r=byid[cid]
        n=sum(e['check_count'] for e in evidence)
        limits='仅当前正式/BENCH链接ARM离线检查；模拟输入与时钟；板上完整调度、真实输入/端子、正式实时时序未覆盖。'
        if cid.startswith('T06-'):limits+='分段横轴未完整标数，切换阈值只作代码观察，不能认作规格定案。'
        if cid in ('T06-001','T06-004'):limits+='电热冬季最小输出按用户接受现状记录，不把它改写成原规格对电热的要求。'
        if cid=='T11-103':limits+='观察到全停和低温需共同持续QHS；原文两种解释未定，本例不能据此判规格完全符合。'
        if cid in ('T13-059','T13-060','T13-062'):
            limits+='当前停机中开机指令被丢弃、不排队；正常关完后重新发开机可启动，仅观察此行为，未将指令排队当作规格要求。'
        if cid=='T13-061':limits+='仅覆盖加载请求尚未确认时的撤销，未做满载连续反向命令板上链路。'
        if cid in ('T11-007','T11-015','T11-023','T11-031','T11-039','T11-104','T11-105'):
            limits+='本例要求真实计时，目前仅模拟计时，真实长计时仍未做。'
        actual=f'仅ARM离线：{r["测试名称"]}，当前双档检查{n}条符合；范围从“{evidence[0]["first_check"]}”至“{evidence[-1]["last_check"]}”。'
        data[cid]={'status':'部分通过','actual':actual,'evidence':evidence[0]['file'],
            'restored':limits,'inputs':'ARM模拟输入/时间，无板上刺激','at':now(),'history':[],
            'offline_supplements':evidence,'evidence_level':'仅ARM离线'}
        r.update({'执行结论':'部分通过','实际结果':actual,'证据文件及时间戳':'; '.join(e['file'] for e in evidence),
            '恢复回读结果':limits,'测试输入实测值':'ARM模拟输入/时间，无板上刺激','执行人及时间':'Codex @ '+now(),
            '本次版本及SHA256':'330V10.52/316V12.39双档链接ARM；非实板结果'})
    dump(RESULTS,data)
    tmp=CASECSV.with_suffix('.csv.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    tmp.replace(CASECSV)
    lines=['# 内机测试版逐项测试记录（2026-11-05）','',
        '压机动力隔离。软件回读不等于端子测量；仅ARM离线已单独标明，部分通过仍有验收缺口。',
        '勾选只表示执行过所列检查，不能表示全部实机验收通过。','',
        '|执行|用例|结论|本次实际结果|恢复/剩余缺口|证据|','|---|---|---|---|---|---|']
    esc=lambda s:str(s).replace('|','／').replace('\n',' ')
    for cid,v in sorted(data.items()):
        lines.append(f'|[x]|{cid}|{esc(v["status"])}|{esc(v["actual"])}|{esc(v["restored"])}|[{cid}]({v["evidence"]})|')
    REPORT.write_text('\n'.join(lines)+'\n','utf8')
    manifest=json.loads((D/'remaining_529_manifest.json').read_text('utf8'))
    pending_ids={r['用例编号'] for r in manifest['cases']}
    coverage=[]
    for cid in sorted(pending_ids):
        r=byid[cid];v=data.get(cid)
        level='仅ARM离线' if v and v.get('evidence_level')=='仅ARM离线' else '板上软件检查/范围见证据' if v else '未执行'
        coverage.append({'用例编号':cid,'模块':r['模块'],'测试名称':r['测试名称'],'本批证据层级':level,
            '验收结论':v['status'] if v else '未执行','实际检查':v['actual'] if v else '',
            '未完成内容':v['restored'] if v else r['逐步操作'],
            '证据':v['evidence'] if v else ''})
    inventory=R/'剩余529例执行覆盖与未测清单_20261105.csv'
    with inventory.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(coverage[0]));w.writeheader();w.writerows(coverage)
    counts=collections.Counter(c['本批证据层级'] for c in coverage)
    summary={'at':now(),'original_pending':529,'new_offline_rows_imported':additions,
        'pending_scope_evidence_counts':dict(counts),'overall_cases_recorded':len(data),
        'overall_status':dict(collections.Counter(v['status'] for v in data.values())),
        'checks_in_matrices':checks_total,'not_all_529_complete':True}
    dump(D/'remaining529_coverage_summary.json',summary)
    # Preserve the plan and replace only its existing live-progress block.
    plan=R/'明日实机验证方案_内机3.1-3.11_20261105.md'
    start='<!-- BENCH_EXECUTION_START -->';end='<!-- BENCH_EXECUTION_END -->'
    progress=start+'\n## 测试执行进度\n\n'+f'更新时间：{now()}。记录{len(data)}例；原529例当前证据层级：{dict(counts)}。仅ARM离线及部分通过均不代表完整实机通过。\n\n'
    progress+='[逐项记录](内机测试版逐项测试记录_20261105.md)；[原529例逐项覆盖与未测清单](剩余529例执行覆盖与未测清单_20261105.csv)。\n\n'
    progress+='\n'.join(f'- [x] {cid}：{v["status"]}'+('（仅ARM离线）' if v.get('evidence_level')=='仅ARM离线' else '') for cid,v in sorted(data.items()))+'\n'+end
    content=plan.read_text('utf8')
    assert start in content
    plan.write_text(re.sub(re.escape(start)+'.*?'+re.escape(end),lambda _:progress,content,flags=re.S),'utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
