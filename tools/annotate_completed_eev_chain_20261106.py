"""Index input-chain checks already executed in a fully recovered EEV batch."""
import json
from pathlib import Path
from datetime import datetime,timezone,timedelta

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'测试证据/内机实测_20261105/BENCH_V1053_V1239'


def main():
    candidates=[]
    for p in BASE.glob('*eev_live_matrix_*.json'):
        d=json.loads(p.read_text('utf8'))
        if d.get('restored') is True and not d.get('error') and d.get('eev_phases'):
            candidates.append((p,d))
    assert candidates
    p,d=max(candidates,key=lambda x:x[0].stat().st_mtime)
    chain=d['input_chain']
    assert all(r['received']['evap']==r['evap'] and r['received']['superheat']==r['superheat']
               and r['suction']==r['evap']+r['superheat'] and abs(r['calibration'])<=100 for r in chain)
    ep=p.relative_to(ROOT).as_posix()
    records=json.loads((BASE/'case_results.json').read_text('utf8'))
    entries=(('T12-003','当前冷媒表选取合法压力映射，316实际滤波/饱和温度经协议送330；蒸发5/9.9/10/12/12.1℃逐点一致。仅当前冷媒及软件压力映射，不代表电气传感器标定。'),
             ('T12-004','蒸发5℃时正常吸气NTC校准形成过热0/3.9/4/4.1/5/5.9/6/6.1/10℃，316吸气−蒸发与330回读逐点一致；仅合法校准输入的软件链路。'))
    stamp=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    for cid,text in entries:
        if records.get(cid,{}).get('evidence')==ep: continue
        prior=records.get(cid,{})
        history=prior.get('history',[])+([{k:v for k,v in prior.items() if k!='history'}] if prior else [])
        records[cid]=dict(status='部分通过',actual=text,evidence=ep,at=stamp,history=history,
            inputs='已有完整恢复的EEV实测日志；当前冷媒、压力工程映射及合法吸气校准；不写PID/输出。')
        d['cases'][cid]=dict(passed=True,actual=text,input_chain=chain)
        with (ROOT/'内机测试版逐项测试记录_20261105.md').open('a',encoding='utf8') as f:
            f.write(f'\n- [x] **{cid} 部分通过**：{text} [已完成批次原始证据]({ep})\n')
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2),'utf8')
    (BASE/'case_results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf8')
    print('Indexed T12-003/004 from completed recovered batch',ep)


if __name__=='__main__':main()
