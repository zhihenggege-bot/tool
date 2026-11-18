"""Record absent prerequisites without overwriting earlier observations."""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'测试证据/内机实测_20261105/BENCH_V1053_V1239'


def main():
    manifest=json.loads((BASE/'remaining_571_manifest.json').read_text('utf8'))
    rows=[]
    for r in manifest['cases']:
        cid=r['用例编号']
        reason=None
        if r['大组']=='T18': reason='当前仅可ST-Link复位，无电脑可控真实断电；不能用复位替代掉电/保存中断验收。'
        elif r['大组']=='T14': reason='用户本轮指定BENCH测试版；不能据加速版验收正式档秒数。保留正式档另测，当前不换刷。'
        elif cid in ('T08-007','T08-008'): reason='缺可确认协议/通道接线的实际电压电流信号源；工程映射模拟不能替代实际低/中/高电气换算。'
        elif cid in ('T10-020','T15-005','T15-006','T15-007','T15-008'):
            reason='当前只有两块316，共4个物理回路；本例要求四外机/第5～8回路，缺额外两块316或已验证的逐站行为模拟器。'
        elif cid in ('T10-025','T10-026','T10-027'):
            reason='当前无已确认的可遥控分路RS485断连开关；不把停止内核或软件故障位写入冒充物理断线/重连。当前按用户指令跳过，其它用例继续。'
        if reason:rows.append(dict(id=cid,name=r['测试名称'],decision='本轮条件不具备，跳过',reason=reason,prior_evidence_retained=True))
    completed=[]
    for path in sorted(BASE.glob('*default_ambient_preheat_*.json')):
        data=json.loads(path.read_text('utf8'))
        if data.get('restored') is True: completed.append((path,data))
    names={r['用例编号']:r['测试名称'] for r in manifest['cases']}
    cooled=set()
    for path in BASE.glob('*serial_environment_cool_targets_*.json'):
        data=json.loads(path.read_text('utf8'))
        if data.get('restored') is True:
            cooled.update(cid for cid,e in data.get('cases',{}).items() if e.get('passed') is True)
    if completed:
        path,data=completed[-1]
        for cid,detail in data.get('unreachable_cases',{}).items():
            rows.append(dict(id=cid,name=names[cid],decision='本轮条件不具备，跳过',
                reason=detail['decision']+f"；当前原始新风约{detail['raw_temperature']/10:.1f}℃。",
                evidence=path.relative_to(ROOT).as_posix(),prior_evidence_retained=True))
        unavailable=list(data.get('unreachable_cases',{}).values())
        if unavailable:
            raw=unavailable[0]['raw_temperature']
            points=(219,220,221,252,253,285,317,318,349,350,351)
            for i,temp in enumerate(points):
                if abs(temp-raw)>100 and f'T09-{i+1:03d}' not in cooled:
                    cid=f'T09-{i+1:03d}'
                    rows.append(dict(id=cid,name=names[cid],decision='本轮条件不具备，跳过',
                        reason=f'默认环境制冷目标点{temp/10:.1f}℃，本批测得原始新风{raw/10:.1f}℃，超出合法±10℃校准范围；继续其它测试。',
                        evidence=path.relative_to(ROOT).as_posix(),prior_evidence_retained=True))
    doc=dict(at=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
             user_instruction='不要停了 接着测试 没办法测试的就跳过',
             scope='本轮环境依赖；不把已知缺硬件的项目标通过，也不覆盖原失败或历史证据',cases=rows)
    (BASE/'environment_skips_20261106.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),'utf8')
    lines=['# 本轮环境不具备而跳过的项目（2026-11-06）','',doc['scope']+'。','',
           f'共{len(rows)}例。其余项目继续执行，不因这些项目等用户操作。','',
           '|用例|项目|跳过原因|','|---|---|---|']
    lines += [f'|{r["id"]}|{r["name"]}|{r["reason"]}|' for r in rows]
    (ROOT/'本轮跳过项目_内机BENCH_20261106.md').write_text('\n'.join(lines)+'\n','utf8')
    print(json.dumps(dict(skipped=len(rows)),ensure_ascii=False))


if __name__=='__main__':main()
