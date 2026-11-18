"""Review completed cycle evidence only; no serial or SWD access."""
import json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'测试证据/内机实测_20261105/BENCH_V1055_V1239/remaining571_heat_dynamic_continuous_thirty_normal_cycles_20261106_130302.json'
d=json.loads(source.read_text('utf8'));e=d['cases']['T13-063'];runs=e['runs']
assert len(runs)==30 and e['passed'] and d['restored'] and not d['restore_mismatches']
checks=[]
for r in runs:
    active,stopped=r['running'],r['stopped']
    check=dict(mode=r['mode'],round=r['round'],duration_s=r['duration_s'],
        started=r['started'],running_fans=all(active['do'][i] for i in (3,6,8)),
        running_thermal_ao_off=all(active['ao'][i]==0 for i in (0,1,2,8,9)),
        stopped_state=stopped['state'][9]==0,
        stopped_do=all(v==0 for i,v in enumerate(stopped['do']) if i!=5),
        stopped_ao=not any(stopped['ao']),
        outdoor_feedback_off=all(v==0 for s in (active,stopped) for pair in s['outdoor_status'] for v in pair),
        fault_free=not any(active['faults']) and not any(stopped['faults']))
    check['passed']=r['passed'] and all(v for k,v in check.items() if k not in ('mode','round','duration_s','started'))
    checks.append(check)
assert all(r['passed'] for r in checks)
out=source.parent/'thirty_cycles_independent_review_20261109.json'
out.write_text(json.dumps(dict(source=source.relative_to(ROOT).as_posix(),read_only_file_review=True,
    additional_board_case_credit=0,passed=True,checks=checks),ensure_ascii=False,indent=2),encoding='utf8')
lines=['# 普通启停30轮复核（内机V10.55，2026-11-09）','',
    'T13-063：通风、制冷、制热各10轮，30轮正常启停的软件检查完成。参数恢复无差异，三板为330 V10.55 / 316 V12.39 BENCH。', '',
    '这是无热湿需求的启停循环：验证三风机动作、停机输出归零、外机停止反馈及故障状态。未覆盖带负载压机循环、端子测量、真实断电或正式保护秒数。', '',
    '|模式|完成轮数|最短/最长（秒）|平均（秒）|结论|','|---|---:|---|---:|---|']
for mode,label in ((2,'通风'),(0,'制冷'),(1,'制热')):
    group=[r for r in checks if r['mode']==mode];times=[r['duration_s'] for r in group]
    assert len(group)==10
    lines.append(f'|{label}|10/10|{min(times):.2f} / {max(times):.2f}|{statistics.mean(times):.2f}|所列软件检查通过|')
lines+=['','制热每轮约112～113秒，包含未缩短的停机吹扫；实际历时原样保留。文件复核不增加实测用例数。', '',
    '|状态|模式|轮次|开始|总历时（秒）|','|---|---|---:|---|---:|']
for r in checks:
    lines.append(f'|[x]|'+{2:'通风',0:'制冷',1:'制热'}[r['mode']]+f'|{r["round"]}|{r["started"]}|{r["duration_s"]:.2f}|')
lines+=['',f'[原始板上记录]({source.relative_to(ROOT).as_posix()}) · [独立文件复核]({out.relative_to(ROOT).as_posix()})','']
text='\n'.join(lines);assert '\ufffd' not in text
(ROOT/'普通启停30轮_内机V10.55_20261109.md').write_text(text,encoding='utf8')
print('30 cycles independently reviewed; no extra test credit; report written')
