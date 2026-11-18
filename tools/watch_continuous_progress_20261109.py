"""Read-only journal watcher; never opens serial or SWD."""
import argparse,json,time
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'测试证据/内机实测_20261105/BENCH_V1055_V1239'
REPORT=ROOT/'持续测试进度_内机V10.55_20261109.md'

def read(path):
    try:return json.loads(path.read_text('utf8'))
    except (OSError,ValueError):return {}

def update(first,follow):
    q=read(first);f=read(follow)
    lines=['# 内机V10.55持续测试进度（2026-11-09）','',
        '更新时间：'+datetime.now().astimezone().isoformat(timespec='seconds'),' ',
        '330 V10.55、两块316 V12.39，均为BENCH。仅一个串口测试进程操作COM6；后续进程等待前批完成和恢复后接续。', '',
        '以下勾选仅表示所述软件子范围已完成并恢复配置，不代表整个用例验收通过。实际接点、端子、真实断电及正式时序另验。', '',
        '## 专用阶段连续队列','',
        '|状态|用例|实际子范围|批次开始|结束|证据|','|---|---|---|---|---|---|']
    complete=0
    for row in q.get('groups',[]):
        evidence=row.get('evidence','');d=read(ROOT/evidence) if evidence else {}
        checked=row.get('status')=='completed' and d.get('restored') is True
        complete+=int(checked)
        state='[x] 已完成并恢复' if checked else row.get('status','等待')
        lines.append(f'|{state}|{row["id"]}|{row["name"]}|{row["started"]}|{row.get("finished","")}|'+(f'[日志]({evidence})' if evidence else '本项进行中，未计通过')+'|')
    lines+=['',f'当前专用阶段队列：{complete}/7组完成并恢复。未开始的组不计通过。','',
        '## 后续连续队列','',
        '顺序：四类反向启停命令 → 30种有向模式切换 → 自动模式单有效阶段/两种结束选择 → 时长参数边界 → 30轮普通启停 → 真实2小时通风监视。','',
        '|项目|状态|开始|结束|','|---|---|---|---|']
    for row in f.get('actions',[]):
        lines.append(f'|{row["name"]}|{row["status"]}|{row.get("started","")}|{row.get("finished","")}|')
    if not f.get('actions'):lines+=['|后续队列|等待前批完成，不占用COM6|||']
    for row in f.get('actions',[]):
        if row.get('error'):lines+=['',f'异常保留：{row["name"]}','```text',row['error'],'```']
    lines+=['','前期22组子场景及修复、编译、烧录校验证据见[V10.55报告](V10.55_特殊阶段显示修复及续测_20261109.md)。',
        '本页只根据原始队列日志更新；未将正在运行或环境受限项目勾成通过。', '',
        f'[前批队列日志]({first.relative_to(ROOT).as_posix()}) · [后续队列日志]({follow.relative_to(ROOT).as_posix()})','']
    text='\n'.join(lines);assert '\ufffd' not in text
    REPORT.write_text(text,encoding='utf8')
    return bool(f.get('finished'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--first',type=Path,required=True);p.add_argument('--follow',type=Path,required=True);a=p.parse_args()
    while True:
        if update(a.first.resolve(),a.follow.resolve()):break
        time.sleep(15)
