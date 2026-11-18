"""Rebind existing regressions to new AXFs, retaining historical scripts/evidence."""
import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path

from test_defrost_lifecycle_arm import ROOT

PACKAGE = ROOT / '.codex-tmp/issuefix_v1059_v1241_20261111'
DEST = ROOT / '测试证据/修复回归_20261111'


def load(name, replacements=()):
    p = ROOT / 'tools' / (name + '.py')
    source = p.read_text('utf-8')
    for old, new in replacements:
        assert old in source, old
        source = source.replace(old, new)
    namespace = {'__name__': 'rebound_' + name, '__file__': str(p)}
    exec(compile(source, str(p), 'exec'), namespace)
    return namespace


def main():
    DEST.mkdir(exist_ok=True)
    suite = sys.argv[1]
    with (DEST / (suite + '.log')).open('w', encoding='utf8') as log, contextlib.redirect_stdout(log):
        if suite == 'shared':
            n = load('test_shared_type_arm_20261110', [('V10.58', 'V10.59'), ('V12.40', 'V12.41')])
            n['PACKAGE'] = PACKAGE
            n['DEST'] = DEST / 'shared'
            n['main']()
            result = dict(total=len(n['ROWS']), passed=sum(r['passed'] for r in n['ROWS']))
        elif suite == 'protection':
            n = load('test_four_outdoor_fixes_arm')
            for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
                n['audit'].OUT = n['lifecycle'].OUT = PACKAGE/profile/f'PSC316_V12.41_{profile}.axf'
                n['lifecycle'].IN = PACKAGE/profile/f'PSC330_V10.59_{profile}.axf'
                for name in ('emergency', 'timed', 'fans', 'fan_scans', 'parameters'):
                    n[name](profile)
            result=dict(total=len(n['RESULTS']), passed=sum(r['passed'] for r in n['RESULTS']), rows=n['RESULTS'])
            assert result['total'] == result['passed'], 'Inspect individual protection regressions'
        elif suite == 'lifecycle':
            results = []
            for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
                replacements = [] if profile == 'PRODUCTION' else [
                    ('tick(o, 59)', 'tick(o, 4)'),
                    ('59 seconds:', '4 BENCH seconds:'),
                    ('60 seconds:', '5 BENCH seconds:'),
                ]
                # The original harness predates the separate BENCH profile.
                n = load('test_defrost_lifecycle_arm', replacements)
                n['OUT'] = PACKAGE/profile/f'PSC316_V12.41_{profile}.axf'
                n['IN'] = PACKAGE/profile/f'PSC330_V10.59_{profile}.axf'
                n['passed'] = 0
                n['main']()
                results.append(dict(profile=profile, passed=n['passed']))
            result=dict(total=sum(r['passed'] for r in results), passed=sum(r['passed'] for r in results), profiles=results)
        elif suite == 'comm':
            n = load('test_comm_poll_health_arm', [
                ('.codex-tmp/sequence_timing_v1047_v1238_20261104/', '.codex-tmp/issuefix_v1059_v1241_20261111/'),
                ('V10.47', 'V10.59')])
            result=dict(total=len(n['checks']), passed=len(n['checks']))
        else:
            raise ValueError(suite)
    result.update(hardware_access=False, suite=suite,
                  artifacts={str(p.relative_to(PACKAGE)):hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in PACKAGE.glob('*/*.axf')})
    (DEST/(suite+'_results.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(suite, result['passed'], '/', result['total'], 'passed')


if __name__ == '__main__':
    main()
