"""Rebind relevant offline regressions to V10.61; keep historical evidence."""
import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / '.codex-tmp/ambient_scope_v1061_20261112'
DEST = ROOT / '测试证据/环境联锁修复_20261112/preservation'


def load(name, replacements=()):
    p = ROOT / 'tools' / (name + '.py')
    source = p.read_text('utf8')
    for old, new in replacements:
        assert old in source, old
        source = source.replace(old, new)
    namespace = dict(__name__='rebound_' + name, __file__=str(p))
    exec(compile(source, str(p), 'exec'), namespace)
    return namespace


def main():
    suite = sys.argv[1]
    DEST.mkdir(parents=True, exist_ok=True)
    with (DEST / (suite + '.log')).open('w', encoding='utf8') as log, contextlib.redirect_stdout(log):
        if suite == 'shared':
            n = load('test_shared_type_arm_20261110', [('V10.58', 'V10.61'), ('V12.40', 'V12.43')])
            n['PACKAGE'] = PACKAGE
            n['DEST'] = DEST / 'shared'
            n['main']()
            result = dict(total=len(n['ROWS']), passed=sum(r['passed'] for r in n['ROWS']))
        elif suite == 'mirror':
            n = load('test_issuefix_arm_20261111', [('10.59', '10.61'), ('12.41', '12.43')])
            n['PACKAGE'] = PACKAGE
            n['DEST'] = DEST
            for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
                n['PROFILE'] = profile
                for name in ('pages', 'polling', 'polling_four_units'):
                    n[name]()
            result = dict(total=len(n['ROWS']), passed=sum(r['passed'] for r in n['ROWS']), rows=n['ROWS'])
        elif suite == 'lifecycle':
            profiles = []
            for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
                replacements = [] if profile == 'PRODUCTION' else [
                    ('tick(o, 59)', 'tick(o, 4)'),
                    ('59 seconds:', '4 BENCH seconds:'),
                    ('60 seconds:', '5 BENCH seconds:'),
                ]
                n = load('test_defrost_lifecycle_arm', replacements)
                n['OUT'] = PACKAGE / profile / f'PSC316_V12.43_{profile}.axf'
                n['IN'] = PACKAGE / profile / f'PSC330_V10.61_{profile}.axf'
                n['main']()
                profiles.append(dict(profile=profile, passed=n['passed']))
            result = dict(total=sum(p['passed'] for p in profiles),
                          passed=sum(p['passed'] for p in profiles), profiles=profiles)
        elif suite == 'restart':
            n = load('test_restart_guard_arm_20261112', [('V10.60', 'V10.61')])
            n['B'] = PACKAGE
            n['D'] = DEST / 'restart_detail.json'
            n['main']()
            result = dict(total=len(n['ROWS']), passed=sum(r['passed'] for r in n['ROWS']))
        else:
            raise ValueError(suite)
    assert result['total'] == result['passed'], result
    result.update(hardware_access=False, suite=suite, package=str(PACKAGE))
    (DEST / (suite + '_results.json')).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(suite, result['passed'], '/', result['total'], 'passed', flush=True)


if __name__ == '__main__':
    main()
