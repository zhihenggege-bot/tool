"""Derive reviewable edge/error tables without altering raw capture."""
import csv
import json
from pathlib import Path

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/缺口复测_20261113'


def main():
    edges=[];errors=[];last={};counts={};previous={};gaps={}
    with (D/'events.jsonl').open(encoding='utf8') as f:
        for lineno,line in enumerate(f,1):
            q=json.loads(line);kind=q['kind'];counts[kind]=counts.get(kind,0)+1
            if kind in ('protocol_error','action_exception'):
                errors.append(dict(at=q['at'],t=q['t'],kind=kind,case=q.get('case',q.get('action','')),
                    args=json.dumps(q.get('args',[])),error=q.get('error'),raw_line=lineno))
            if kind!='direct_and_mirror':continue
            s=q['sample'];key=s['label']
            gap=s['t']-previous[key] if key in previous else 0
            previous[key]=s['t'];gaps[key]=max(gaps.get(key,0),gap)
            row=dict(at=s['at'],t=s['t'],case=key,mode=s['selected_mode'],step=s['state'][9],owner=s['owner'],
                pending=s.get('IndoorPendingWorkMode'),active_mode=s.get('IndoorActiveWorkMode'))
            for index,b in enumerate(s['boards'],1):
                row[f'unit{index}_output']=b['output']
                row[f'unit{index}_phase']=b['phase']
                row[f'unit{index}_mirror_phase']=b['mirror_phase']
                row[f'unit{index}_defrost_state']=b['PSC316DefrostState']
                row[f'unit{index}_active_faults']=[600+i for i,v in enumerate(b['alarms']) if v]
            signature={k:v for k,v in row.items() if k not in ('at','t')}
            if last.get(key)!=signature:
                last[key]=signature;row['raw_line']=lineno;edges.append(row)
    def table(path,rows):
        if not rows:return
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader()
            for row in rows:w.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in row.items()})
    table(D/'state_edges.csv',edges);table(D/'protocol_and_action_errors.csv',errors)
    q=dict(event_counts=counts,total_events=sum(counts.values()),state_edges=len(edges),
        exceptions=len(errors),max_direct_sample_gaps_s=gaps,
        note='Max gaps include separate attempts with the same label; use raw line/timestamps for each bounded observation. No assumption that unobserved intervals remained unchanged.')
    (D/'capture_statistics.json').write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8')
    print(q)


if __name__=='__main__':main()
