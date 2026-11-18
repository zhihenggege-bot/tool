"""Exactly five batches for the four requested follow-ups, then stop."""
import json
from pathlib import Path
import subprocess
import sys
import time

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/四项复核_20261112'
PAUSE=R/'.codex-tmp/four_followups_pause.request'
PLAN=[('fixed50Hz_span',['scaling']),('fan_and_contact_protection',['contacts']),
      ('fixed_two_speed_cooling',['typeII']),('restart_60',['minrun','--value','60']),
      ('restart_120',['minrun','--value','120'])]

def now():return time.strftime('%Y-%m-%dT%H:%M:%S%z')

def main():
    path=D/('four_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),status='running',scope='Only four follow-ups; full queue and two-hour soak remain paused',
        tasks=[dict(key=k,arguments=a) for k,a in PLAN],completed=[],steps=[])
    def save():
        p=path.with_suffix('.tmp');p.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8');p.replace(path)
        lines=['# 四项复核进度（2026-11-12）','',
            '330 V10.59／316 V12.42 BENCH。仅四项复核；全日剩余队列及连续2小时测试保持暂停。','',
            f'更新时间：{now()}；状态：{q["status"]}。执行完不代表全部通过，需核各用例证据。','',
            '|批次|开始|结束|进程返回码|','|---|---|---|---|']
        for s in q['steps']:lines.append(f'|{s["key"]}|{s["started"]}|{s.get("finished","执行中")}|{s.get("exitcode","")}|')
        lines+=['','证据目录：`测试证据/四项复核_20261112`。软件DO/AO回读不等于端子电压实测。']
        (R/'四项复核进度_20261112.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    def call(key,args):
        log=D/(path.stem+'_'+key+'.log');s=dict(key=key,arguments=args,started=now(),output=str(log.relative_to(R)))
        q['steps'].append(s);save()
        with log.open('w',encoding='utf8') as out:
            p=subprocess.Popen([sys.executable,'-X','utf8','-u','tools/bench_four_followups_20261112.py',*args],cwd=R,stdout=out,stderr=subprocess.STDOUT)
            s['pid']=p.pid;save();s['exitcode']=p.wait()
        s['finished']=now();save();return s['exitcode']
    def audit(label):
        for i in range(3):
            if call(label+'_'+str(i),['audit'])==0:return
        raise RuntimeError('Restoration audit failed; no next stimulus')
    try:
        save();audit('initial_audit')
        for key,args in PLAN:
            if PAUSE.exists():q['status']='paused_by_user';break
            call(key,args);audit('after_'+key+'_audit')
            q['completed'].append(key);save()
        if q['status']=='running':q['status']='finished_review_case_results'
    except BaseException as ex:q.update(status='restoration_or_controller_error',error=repr(ex));raise
    finally:q['finished']=now();save()

if __name__=='__main__':main()
