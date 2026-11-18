"""Read saved evidence only; no serial/debugger access."""
import json
from pathlib import Path

D = Path(__file__).resolve().parents[1] / '测试证据/四项复核_20261112'

for p in sorted(D.glob('four_controller_*.json')):
    q = json.loads(p.read_text('utf8'))
    print('CONTROLLER', p.name, q['status'], q.get('completed'))
    for s in q['steps'][-2:]:
        print('  STEP', s['key'], s.get('started'), s.get('finished', 'RUNNING'), s.get('exitcode'))
for p in sorted(D.glob('*.json')):
    try:
        q = json.loads(p.read_text('utf8'))
    except (ValueError, OSError):
        continue
    if not isinstance(q, dict):
        continue
    for key in ('scaling', 'B01_contacts', 'remaining_functional'):
        e = q.get(key)
        if not e:
            continue
        print('EVIDENCE', p.name, key, 'error=', e.get('error', '')[-250:])
        for c in e.get('cases', []):
            print(' ', c.get('label', c.get('ch', c.get('maximum_hz'))),
                  c.get('passed', c.get('status', 'IN PROGRESS')),
                  c.get('error', ''), 'restored=', c.get('recovery_verified'))
        for c in e.get('pairs', []):
            print('  PAIR', c.get('pair'), 'error=', c.get('error', '')[-250:],
                  'runs=', c.get('run_lengths'), 'gaps=', c.get('restart_gaps'))
