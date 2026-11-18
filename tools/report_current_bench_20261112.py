"""Summarize current-board evidence without opening serial/debug connections."""
import json
from pathlib import Path
import time
import argparse
import csv
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
DAY=ROOT/'测试证据/台架执行_20261112'

def minimum_run_observations():
    """Keep completed output-edge evidence even when a later restart times out."""
    observations=[]
    for p in sorted(DAY.glob('remaining_normal_prestart_six_pairs_*.json')):
        try:d=json.loads(p.read_text('utf8'))
        except (OSError,ValueError):continue
        section=d.get('remaining_functional',{})
        setting=section.get('minimum_seconds')
        for row in section.get('pairs',[]):
            pair=row.get('pair')
            if pair!=[2,4]:continue
            samples=row.get('initial_start',[])+row.get('initial_run',[])+row.get('normal_unload',[])
            runs=[]
            for fan,output_index in enumerate((2,3)):
                on=[i for i,s in enumerate(samples) if s['output'][output_index]]
                if not on:continue
                first,last=on[0],on[-1]
                off=next((i for i in range(last+1,len(samples)) if not samples[i]['output'][output_index]),None)
                if off is None:continue
                duration=samples[off]['t']-samples[first]['t']
                start=[samples[first-1]['t'],samples[first]['t']] if first else None
                stop=[samples[last]['t'],samples[off]['t']]
                runs.append(dict(fan=fan,on_seconds=round(duration,3),
                    shortfall_seconds=round(max(0,setting-duration),3),
                    signed_difference_seconds=round(duration-setting,3),
                    duration_bounds_seconds=([round(stop[0]-start[1],3),round(stop[1]-start[0],3)] if start else None)))
            observations.append(dict(setting_seconds=setting,pair=pair,runs=runs,
                later_error=row.get('error'),restored=d.get('restored',False),
                evidence=p.relative_to(ROOT).as_posix(),
                limitation='软件边沿观察；正常卸载延迟可能延长运行；重新加载结果单列，不据此判定完整用例通过。'))
    return observations

def main():
    records=[]
    for p in sorted(DAY.glob('*.json')):
        if p.name.startswith(('controller_','current_controller_')):continue
        try:d=json.loads(p.read_text('utf8'))
        except (OSError,ValueError):continue
        if not isinstance(d,dict):continue
        for group in ('B01','B01_contacts','remaining_functional','parameter_matrix'):
            section=d.get(group,{})
            for r in section.get('cases',[]):
                status=r.get('status')
                if status is None:
                    result=r.get('passed',r.get('software_scope_passed'))
                    status=('软件子范围通过' if result else '实测有待核对') if result is not None else '执行中／仅观察'
                records.append(dict(id=r.get('id',''),label=r.get('label',group),status=status,
                    evidence=p.relative_to(ROOT).as_posix(),restored=d.get('restored',False),
                    detail={k:v for k,v in r.items() if k not in ('samples','healthy','hold','recovery','source_edge','segments','points') and not isinstance(v,(dict,list))}))
            for r in section.get('events',[]):
                if 'id' in r:records.append(dict(id=r['id'],label=r.get('label',''),status='软件子范围通过' if r.get('passed') else '实测有待核对',evidence=p.relative_to(ROOT).as_posix(),restored=d.get('restored',False),detail={}))
            for r in section.get('pairs',[]):
                if not r.get('error'):continue
                index=((0,0),(0,1),(1,2),(1,3),(2,2),(2,4)).index(tuple(r['pair']))
                records.append(dict(id=f'O-FANTIME-{index*4+2:03d}',label=section.get('kind','')+'_incomplete_restart',
                    status='实测有待核对',evidence=p.relative_to(ROOT).as_posix(),restored=d.get('restored',False),
                    detail=dict(error=r['error'])))
    controllers=sorted(DAY.glob('current_controller_*.json'),key=lambda p:p.stat().st_mtime)
    states=[json.loads(p.read_text('utf8')) for p in controllers]
    active=[s for s in states if s.get('status')=='running' and
        (not s.get('waiting_for_predecessor') or s.get('predecessor_finished'))]
    controller=dict((active or states or [{}])[-1])
    controller['completed']=[k for s in states for k in s.get('completed',[])]
    controller['tasks']=[t for s in states for t in s.get('tasks',[])]
    if any(s.get('status')=='running' for s in states):controller['status']='running'
    controller['batch_execution_errors']=[step for s in states for step in s.get('steps',[]) if step.get('exitcode',0)!=0]
    grouped=defaultdict(list)
    for r in records:grouped[r['id']].append(r)
    candidate=ROOT/'内外机台架续测清单_20261112.csv.txt'
    with candidate.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f));fields=list(rows[0])
    for row in rows:
        measured=grouped.get(row['用例'],[])
        if not measured:continue
        all_restored=all(r['restored'] for r in measured)
        statuses={r['status'] for r in measured}
        row['明日执行状态']='本日已测软件子范围；完整验收缺口仍保留'
        row['明日结果']='；'.join(sorted(statuses))+'；不代表原行全部验收范围已关闭'
        row['明日证据']='；'.join(sorted({r['evidence'] for r in measured}))
        row['恢复核验']='对应批次均已恢复读回' if all_restored else '本批执行中／尚未核验完成，见证据'
    target=ROOT/'内外机台架续测结果_20261112.csv.txt'
    temp=target.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    temp.replace(target)
    q=dict(updated=time.strftime('%Y-%m-%dT%H:%M:%S%z'),records=records,
        controller=controller,controller_phases=states,software_subscopes_only=True,
        minimum_run_observations=minimum_run_observations(),
        candidate_rows_with_new_software_evidence=sum(bool(grouped.get(r['用例'])) for r in rows),
        inventory_note='后续执行批次不是用例数；原100行候选清单及306行总账需按覆盖范围逐行核对，不能按采样点扣减。')
    (DAY/'live_status.json').write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# 2026-11-12 内外机台架执行记录','',
        '330 V10.59／316 V12.41，BENCH_ONLY_3S。板上输入模拟和软件输出回读；端子测量、真实断电、正式档时序不在这些通过结论内。','',
        f'更新：{q["updated"]}；连续队列状态：{controller.get("status","未建立")}；已执行并恢复核验的批次：{len(controller.get("completed",[]))}／{len(controller.get("tasks",[]))}。执行完不代表各用例全部通过。',
        '',q['inventory_note'],'',
        f'原100行候选中，已有新增板上软件证据：{q["candidate_rows_with_new_software_evidence"]}行。完整验收仍按原覆盖要求核对：[本日逐行结果](内外机台架续测结果_20261112.csv.txt)。','',
        '环温探头故障时330逐条、分层和锁存均可见；观察到另一外机随后停机，作为独立疑点保留，不能写成健康外机持续运行通过。','',
        '|用例|采样范围|结论|本批参数恢复|证据|','|---|---|---|---|---|']
    for r in records:
        label=str(r['label']).replace('|','／')
        lines.append(f'|{r["id"]}|{label}|{r["status"]}|{"已核验" if r["restored"] else "尚未完成／看原记录"}|[{Path(r["evidence"]).name}]({r["evidence"]})|')
    lines+=['','## 一定一变最小运行时间：已观察边沿','',
        '下表保留重新加载超时之前已经取得的运行时长；不把批次恢复成功计为用例通过。正常卸载等待可能使运行长于设定。','',
        '|设定秒数|两路软件运行秒数|后续环节|恢复|','|---|---|---|---|']
    for item in q['minimum_run_observations']:
        durations='／'.join(str(r['on_seconds']) for r in item['runs']) or '尚未采齐'
        state='重新加载等后续环节异常，见原始证据' if item['later_error'] else '见各子项结果；采样完成前不定案'
        lines.append(f'|{item["setting_seconds"]}|{durations}|{state}|{"已核验" if item["restored"] else "执行中"}|')
    lines+=['','运行队列和原始采样：[本日证据目录](测试证据/台架执行_20261112)。问题留证，按快照恢复并独立读回后继续下一批。']
    (ROOT/'台架执行_20261112.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('CURRENT EVIDENCE RECORDED',len(records),'sampling scopes',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true');args=parser.parse_args()
    while True:
        main()
        if not args.watch:break
        paths=list(DAY.glob('current_controller_*.json'))
        if paths:
            if all(json.loads(p.read_text('utf8')).get('status')!='running' for p in paths):break
        time.sleep(45)
