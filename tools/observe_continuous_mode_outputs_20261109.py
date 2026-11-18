"""Independent read-only journal checks, with no serial/debug connection."""
import json,time
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'测试证据/内机实测_20261105/BENCH_V1055_V1239'
OUT=BASE/'continuous_mode_output_independent_review_20261109.json'

def review():
    while True:
        files=list(BASE.glob('remaining571_heat_dynamic_continuous_thirty_mode_transitions_v1055_*.json'))
        if not files:time.sleep(5);continue
        path=max(files,key=lambda v:v.stat().st_mtime)
        try:d=json.loads(path.read_text('utf8'))
        except (OSError,ValueError):time.sleep(5);continue
        rows=[];mismatches=[];completed=[]
        for cid,e in d.get('cases',{}).items():
            if e.get('passed') is True:completed.append(cid)
            for i,s in enumerate(e.get('samples',[])):
                rows.append(s)
                faults=[]
                if any(s['do'][j] for j in (0,1,2,11,13,14,15)):faults.append('unexpected thermal/humidifier DO')
                if s['do'][10] and s['do'][8]:faults.append('disinfect and exhaust outputs overlap')
                if faults:mismatches.append(dict(case=cid,index=i,issues=faults,sample=s))
        restored=d.get('restored') is True
        report=dict(at=datetime.now().astimezone().isoformat(timespec='seconds'),source=path.relative_to(ROOT).as_posix(),
            hardware_access=False,new_board_execution=False,scope='Independent review of actual live mode-transition samples; no new test credit',
            sampled_rows=len(rows),completed_individual_cases=completed,batch_restored=restored,mismatches=mismatches,
            passed=restored and len(completed)==30 and not mismatches)
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        if mismatches or restored or d.get('cleanup_error'):
            print('MODE OUTPUT REVIEW',report['passed'],'samples',len(rows),'mismatches',len(mismatches),flush=True)
            return
        time.sleep(10)

if __name__=='__main__':review()
