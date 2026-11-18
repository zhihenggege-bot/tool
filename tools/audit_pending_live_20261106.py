"""Read-only inventory of stored per-case evidence, separate board and ARM."""
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / '测试证据/内机实测_20261105'
CURRENT = BASE / 'BENCH_V1053_V1239'


def good(entry):
    if isinstance(entry, list):
        checks = [x for x in entry if isinstance(x, dict) and 'passed' in x]
        return bool(checks) and all(x['passed'] is True for x in checks)
    return isinstance(entry, dict) and entry.get('passed') is True and not entry.get('error')


def recorded_evidence(record):
    """A summary link must not hide restored raw journals retained in history."""
    if not isinstance(record, dict):
        return
    yield record
    for prior in record.get('history', []):
        yield from recorded_evidence(prior)


def main():
    manifest = json.loads((CURRENT / 'remaining_571_manifest.json').read_text('utf8'))
    records = json.loads((CURRENT / 'case_results.json').read_text('utf8'))
    cases = {r['用例编号']: r for r in manifest['cases']}
    evidence = {cid: {'board': [], 'offline': [], 'record': records.get(cid)} for cid in cases}
    for package in sorted(BASE.glob('BENCH_*')):
        for path in sorted(package.glob('*.json')):
            if path.name in ('case_results.json', 'remaining_571_manifest.json'):
                continue
            try:
                data = json.loads(path.read_text('utf8'))
            except (UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or not isinstance(data.get('cases'), dict):
                continue
            offline = (data.get('hardware_access') is False or data.get('time_is_simulated') is True
                       or '_ARM' in path.name or '_arm' in path.name)
            if not offline and data.get('restored') is not True:
                continue
            for cid, entry in data['cases'].items():
                if cid in evidence and good(entry):
                    evidence[cid]['offline' if offline else 'board'].append(path.relative_to(ROOT).as_posix())
    rows = []
    for cid, r in cases.items():
        e = evidence[cid]
        rec = e['record'] or {}
        for observation in recorded_evidence(rec):
            if observation.get('status') not in ('通过', '部分通过', '按用户要求保留'):
                continue
            ep = observation.get('evidence', '')
            text = observation.get('actual', '') + observation.get('inputs', '')
            level = 'offline' if '_ARM' in ep or '仅ARM离线' in text else 'board'
            if ep:
                path = ROOT / ep
                try:
                    source = json.loads(path.read_text('utf8'))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    source = {}
                # A running test can have per-case entries before its finally
                # restores the bench. Only completed recovery is board evidence.
                # Status belongs to this exact per-case observation. Do not
                # infer acceptance from passing PID phases alone: e.g. the
                # phases can pass while a required endpoint remains missing.
                if level == 'offline' or (source.get('restored') is True and
                        cid in source.get('cases', {}) and
                        not (source['cases'][cid].get('error') if isinstance(source['cases'][cid], dict) else False)):
                    e[level].append(ep)
        for kind in ('board', 'offline'):
            e[kind] = list(dict.fromkeys(e[kind]))
        level = '有板上软件证据，仍需按逐项范围验收' if e['board'] else '仅离线证据，板上待测' if e['offline'] else '未找到已完成证据'
        rows.append({'id': cid, 'group': r['大组'], 'name': r['测试名称'], 'level': level,
                     'latest_record_status': rec.get('status', '未记录'), 'evidence': e,
                     'steps': r['逐步操作'], 'requirements': r['设备与条件'], 'criteria': r['逐项合格判据']})
    counts = Counter(r['level'] for r in rows)
    report = {'scope': '此前列为待补测的571例；不把历史基线101例自动当成本轮通过',
              'counts': dict(counts), 'rows': rows,
              'limits': '板上证据仅指所列软件范围，不能替代物理输入/端子/真实断电/正式时序。未找到不等同证实从未做过。'}
    (CURRENT / 'pending_evidence_inventory_20261106.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    lines = ['# 尚待补测项目及证据盘点（2026-11-06）', '', report['scope'] + '。', '', report['limits'], '',
             '|证据范围|例数|', '|---|---:|']
    lines += [f'|{k}|{v}|' for k, v in counts.items()]
    lines += ['', '不同版本和历史证据按JSON路径保留，不能把旧版本板上结果自动算作V10.53回归。'
              '本轮继续测试时逐条更新；旧CSV加密文件保持原样。', '',
              '|用例|项目|仍需板上补测的状态|', '|---|---|---|']
    lines += [f'|{r["id"]}|{r["name"]}|{r["level"]}|' for r in rows if not r['evidence']['board']]
    (ROOT / '尚待补测证据盘点_20261106.md').write_text('\n'.join(lines) + '\n', 'utf8')
    print(json.dumps(dict(scope=571, counts=dict(counts)), ensure_ascii=False))


if __name__ == '__main__':
    main()
