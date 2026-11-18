"""Read journals only; never opens COM6, SWD, or changes test evidence."""
import json
from pathlib import Path
import time

BASE=Path(__file__).resolve().parents[1]/'测试证据/内机实测_20261105/BENCH_V1053_V1239'


def main():
    p=max(BASE.glob('remaining571_heat_dynamic_*_20261106_*.json'),key=lambda p:p.stat().st_mtime)
    for attempt in range(5):
        try:d=json.loads(p.read_text('utf8'));break
        except json.JSONDecodeError:time.sleep(.1)
    cases=d.get('cases',{})
    cid=next(reversed(cases)) if cases else None
    entry=cases.get(cid,{})
    result=dict(journal=p.name,restored=d.get('restored'),case_count=len(cases),
        passed=sum(v.get('passed') is True for v in cases.values() if isinstance(v,dict)),
        latest_case=cid,kind=entry.get('kind'),mode=entry.get('mode'),
        trip_s=entry.get('reaction_observed_s'),latest_passed=entry.get('passed'),
        case_error=entry.get('error'),batch_error=d.get('error'))
    if 'qhs' in entry:
        result.update(qhs=entry['qhs'],latest_counter=entry.get('edges',[{}])[-1].get('switch_count'))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
