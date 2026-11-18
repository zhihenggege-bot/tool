"""Summarize saved input/output and330 watchdog traces, without hardware access."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / '测试证据/四项复核_20261112'


def analyze(path):
    q = json.loads(path.read_text('utf8'))
    e = q.get('remaining_functional', {})
    if not e.get('kind', '').startswith('normal_prestart_'):
        return None
    report = dict(evidence=path.name, setting_s=e['minimum_seconds'], pairs=[])
    for pair in e.get('pairs', []):
        samples = pair.get('normal_reload', [])
        if not samples:
            continue
        start = samples[0]['t']
        last = None
        events = []
        for s in samples:
            diag = s.get('indoor_restart_diagnostics', {})
            commands = [s['params'].get(str(a)) for a in (1400, 1403)]
            retry = diag.get('CompStartRetryUntil', [0]*10)[2:4]
            state = commands + s['output'][:4] + retry
            if state == last:
                continue
            last = state
            tick = diag.get('Systick_1ms', [0])[0]
            events.append(dict(t_relative_s=round(s['t']-start, 3),
                command316=commands, software_Y00_Y03=s['output'][:4],
                watchdog_retry_until_ms=retry,
                watchdog_retry_remaining_s=[round(max(0,v-tick)/1000,3) for v in retry],
                indoor_tick_ms=tick))
        report['pairs'].append(dict(pair=pair['pair'], error=pair.get('error'),
            run_lengths=pair.get('run_lengths'), restart_gaps=pair.get('restart_gaps'), events=events))
    return report


if __name__ == '__main__':
    rows = []
    for p in sorted([*D.glob('*.json'),*(D/'restart_fix').glob('*.json')]):
        if p.name.endswith('_analysis.json'):
            continue
        try:
            result = analyze(p)
        except (AttributeError, TypeError, KeyError, ValueError):
            continue
        if result:
            result['evidence']=p.relative_to(D).as_posix()
            rows.append(result)
    dest = D/'restart_diagnostics_analysis.json'
    dest.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(rows,ensure_ascii=False,indent=2))
