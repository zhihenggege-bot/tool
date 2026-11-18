"""Recheck retained DI traces, including the fan during disinfect/filter cases.

No new stimulus or board access. This is a post-analysis of existing software
samples and cannot qualify electrical contacts or physical output terminals.
"""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'测试证据/内机实测_20261105/BENCH_V1053_V1239'


def running(s,mode):
    if s['state'][9]!=2 or s['do'][3]!=1 or s['ao'][7]<=0:return False
    if mode in (3,5):return s['do'][10]==1 and all(s['ao'][i]==0 for i in (0,1,2,8,9))
    if mode==4:return s['do'][8]==1 and all(s['ao'][i]==0 for i in (0,1,2,8,9))
    if mode==2:return all(s['ao'][i]==0 for i in (0,1,2,8,9))
    return s['ao'][0]>0 and s['ao'][2]>0 and (mode!=1 or s['ao'][1]>0)


def off(s):
    return s['state'][9]==0 and not any(v for i,v in enumerate(s['do']) if i!=5) and not any(s['ao'])


def main():
    rows=[];unfinished=[]
    sources=set(BASE.glob('remaining571_heat_dynamic_di_protection_matrix_*.json'))
    sources.update(BASE.glob('remaining571_heat_dynamic_serial_di_protection_matrix_*.json'))
    for p in sorted(sources):
        d=json.loads(p.read_text('utf8'))
        if d.get('restored') is not True:
            unfinished.append(p.name);continue
        for cid,v in d.get('cases',{}).items():
            if not v.get('passed'):continue
            mode,kind=v['mode'],v['kind']
            checks=dict(source_load_established=running(v['before'],mode),
                load_recovers_after_reset=running(v['recovered'],mode))
            if kind=='filter':checks['fans_and_loads_continue_during_filter_alarm']=all(running(s,mode) for s in v['trip_samples'])
            elif kind=='remote':checks['normal_stop_reaches_outputs_off']=off(v['normal_stop'])
            else:checks['latched_protection_stops_outputs']=off(v['trip'])
            rows.append(dict(id=cid,mode=mode,kind=kind,passed=all(checks.values()),checks=checks,
                source=p.relative_to(ROOT).as_posix()))
    report=dict(scope='仅重新分析已恢复批次的原始DI软件样本，未增加板上刺激或物理验收',
        rows=rows,unfinished_sources=unfinished,
        checked=len(rows),unique_case_ids=len({r['id'] for r in rows}),mismatches=sum(not r['passed'] for r in rows))
    (BASE/'di_retained_trace_validation_20261106.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(checked_records=len(rows),unique_case_ids=report['unique_case_ids'],mismatches=report['mismatches'],unfinished=len(unfinished)),ensure_ascii=False))


if __name__=='__main__':main()
