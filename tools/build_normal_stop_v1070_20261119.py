"""Narrow normal-shutdown reconciliation fix; production-only build, no flashing."""
import difflib
import json
from pathlib import Path
import build_timing_profiles as build
from deploy_production_v1064_v1246_20261118 import sha

R = build.ROOT
OUT = R / '.codex-tmp/normal_stop_v1070_20261119'
DAY = R / '测试证据/正常停机请求残留修复_V1070_20261119'
OLD = R / '.codex-tmp/ambient_setting_v1069_v1251_20261119/PRODUCTION'


def inventory():
    return {p.relative_to(R).as_posix(): sha(p)
            for root in ('PSC330RK-V10-内机/User', 'PSC316RK-V12-外机/WELLTHINKER/User',
                         'PSC316RK-V12-外机/WELLTHINKER/modbus')
            for p in (R / root).rglob('*') if p.suffix.lower() in ('.c', '.h')}


def prepare():
    old = json.loads((OLD / 'manifest.json').read_text('utf8'))
    assert all(sha(R / n) == h for n, h in old['source_inventory'].items())
    changes = {
        'PSC330RK-V10-内机/User/UserSrc/CompAction.c': [
            ('/* Cancel a start that has not reached running feedback. A defrosting\n'
             '               unit keeps its requests until it can join normal unloading again. */',
             '/* Normal stop revokes EVERY idle start request, including one that\n'
             '               ran before an autonomous outdoor stop. Confirmed-start tracking\n'
             '               is not proof of current operation. Preserve active defrost and\n'
             '               status 4; actual running compressors still unload sequentially. */'),
            ('(!OutdoorIsDefrosting(module) && !CompIsRunningStatus(module,comp) &&\n'
             '                  CompStartTracked[module][comp] && !CompStartConfirmed[module][comp])',
             '(!OutdoorIsDefrosting(module) && !CompIsRunningStatus(module,comp) &&\n'
             '                  UnitReadStatus[module].CompStatus[comp]!=4)')],
        'PSC330RK-V10-内机/User/UserHead/User.h': [
            ('#define PSC330_VERSION_MINOR        69', '#define PSC330_VERSION_MINOR        70')]
    }
    prepared = {}
    for name, pairs in changes.items():
        before = (R / name).read_bytes()
        nl = '\r\n' if b'\r\n' in before else '\n'
        after = before
        for a, b in pairs:
            a, b = (s.replace('\n', nl).encode('ascii') for s in (a, b))
            assert after.count(a) == 1, (name, a)
            after = after.replace(a, b)
        prepared[name] = before, after
    OUT.mkdir(parents=True)
    DAY.mkdir(parents=True, exist_ok=True)
    (OUT / 'source_before.json').write_text(json.dumps(inventory(), indent=2), 'utf8')
    diff = []
    for name, (before, after) in prepared.items():
        backup = OUT / 'source_backup' / name
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(before)
        (R / name).write_bytes(after)
        diff.extend(difflib.unified_diff(
            before.decode('gb18030', errors='replace').splitlines(True),
            after.decode('gb18030', errors='replace').splitlines(True),
            fromfile=name + ' before', tofile=name + ' after'))
    (OUT / 'task_changes.diff').write_text(''.join(diff).replace('\r\n', '\n'), 'utf8')
    (OUT / 'source_after.json').write_text(json.dumps(inventory(), indent=2), 'utf8')


def main():
    if not OUT.exists():
        prepare()
    elif not (OUT / 'source_after.json').exists():
        # Resume only the diagnostic diff export; mutations already have backups.
        diff = []
        for p in (OUT / 'source_backup').rglob('*'):
            if not p.is_file():
                continue
            name = p.relative_to(OUT / 'source_backup').as_posix()
            diff.extend(difflib.unified_diff(
                p.read_bytes().decode('gb18030', errors='replace').splitlines(True),
                (R / name).read_bytes().decode('gb18030', errors='replace').splitlines(True),
                fromfile=name + ' before', tofile=name + ' after'))
        (OUT / 'task_changes.diff').write_text(''.join(diff).replace('\r\n', '\n'), 'utf8')
        (OUT / 'source_after.json').write_text(json.dumps(inventory(), indent=2), 'utf8')
    inv = json.loads((OUT / 'source_after.json').read_text('utf8'))
    assert inventory() == inv
    build.OUT = OUT
    artifacts = build.build(*build.PROJECTS[0][:-1], '10.70', False, incremental=True)
    assert inventory() == inv
    (OUT / 'PRODUCTION/manifest.json').write_text(json.dumps(dict(
        versions={'330': '10.70', '316_unchanged': '12.51'}, profile='PRODUCTION',
        source_inventory=inv, artifacts=artifacts, flashed=False, hardware_tested=False), indent=2), 'utf8')
    print('PRODUCTION BUILD PASS: 330 V10.70; 316 unchanged', flush=True)


if __name__ == '__main__':
    main()
