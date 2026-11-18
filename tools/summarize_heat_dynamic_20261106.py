"""Read-only evidence interpretation; never modifies original test matrices."""
import json,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'测试证据/内机实测_20261105'

def main():
    selected={}
    for p in sorted(DATA.glob('BENCH_V105[23]_V1239/remaining571_heat_dynamic_*20261106_*.json')):
        d=json.loads(p.read_text('utf8'))
        for cid,c in d.get('cases',{}).items():
            if c.get('assessment') and (cid not in selected or c.get('started','')>=selected[cid][2].get('started','')):
                selected[cid]=(p,d,c)
    out=ROOT/'制热曲线_升降回差明细_20261106.csv'
    rows=[];lines=['# 制热输出曲线板上观测（2026-11-06）','',
        '这是隔离负载BENCH软件回读。AO不是端子电压，DO不是接点独立测量。分段原图未标明的横轴切换数值只列“观测区间”，不倒填为规格。',
        '','|用例|对象/方式|上升档位|下降档位|需求端点|切换/输出异常|批末恢复|','|---|---|---|---|---|---|---|']
    details=[]
    for cid,(p,d,c) in sorted(selected.items()):
        slots=(13,14,15) if c['owner']=='preheat' else (0,1,2)
        channel=1 if c['owner']=='preheat' else 9 if c['owner']=='independent' else 0
        key='preheat' if c['owner']=='preheat' else 'heat'
        levels={direction:sorted({sum(s['do'][idx]*(1<<i) for i,idx in enumerate(slots)) for s in c['rows'] if s['direction']==direction}) for direction in ('up','down')}
        previous={};transitions=[]
        for s in c['rows']:
            direction=s['direction'];level=sum(s['do'][idx]*(1<<i) for i,idx in enumerate(slots))
            row={'用例':cid,'对象':c['owner'],'方式':c['output_mode'],'方向':direction,
                '时间':s['at'],'单调时钟秒':s['t'],'需求':s[key],'AO通道':channel,'AO':s['ao'][channel],
                'DO组1':s['do'][slots[0]],'DO组2':s['do'][slots[1]],'DO组3':s['do'][slots[2]],
                '二进制档位':level,'证据':str(p.relative_to(ROOT))}
            rows.append(row)
            if direction in previous and previous[direction]['二进制档位']!=level:
                prev=previous[direction]
                transitions.append(f'{direction} {prev["二进制档位"]}→{level}：需求由{prev["需求"]}到{s[key]}')
            previous[direction]=row
        missing=[]
        if c['output_mode'] in (2,3):
            all_levels=set(range(2**c['output_mode']))
            for direction in ('up','down'):
                omitted=all_levels-set(levels[direction])
                if omitted:missing.append(f'{direction}未采到平台{sorted(omitted)}，不能算全回差已验证')
        n=[s[key] for s in c['rows']]
        lines.append(f'|{cid}|{c["owner"]}/{c["output_mode"]}|{levels["up"]}|{levels["down"]}|{min(n)}～{max(n)}|{len(c["assessment"]["mismatches"])}；'+('；'.join(missing) if missing else '平台无缺项')+f'|{d.get("restored","进行中")}|')
        details.extend(['',f'**{cid} 切换观测**：'+('；'.join(transitions) or '连续AO，无DO分档切换。'),
            f'原始证据：[JSON]({p.relative_to(ROOT).as_posix()})。',''])
    if rows:
        with out.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (ROOT/'制热曲线_升降回差观测_20261106.md').write_text('\n'.join(lines+details)+'\n',encoding='utf8')
    print('CURVES',len(selected),'SAMPLES',len(rows),flush=True)

if __name__=='__main__':main()
