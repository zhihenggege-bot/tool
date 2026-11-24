"""Add diagnostic-only per-input latches, preserving the existing stop path."""
import difflib
import json
import build_timing_profiles as build
from build_normal_stop_v1070_20261119 import inventory

R = build.ROOT
OLD = R / '.codex-tmp/da8_standby_v1075_20261124/PRODUCTION'
OUT = R / '.codex-tmp/di_faults_v1076_20261124'
DAY = R / '测试证据/DI独立故障_V1076_20261124'


def prepare():
    assert inventory() == json.loads((OLD/'manifest.json').read_text('utf8'))['source_inventory']
    changes = {
        'PSC330RK-V10-内机/User/UserHead/User.h': [
            ('#define PSC330_VERSION_MINOR        75', '#define PSC330_VERSION_MINOR        76'),
            ('#define MainHeatFaultLatchDisp Parameter[966]',
             '/* Per-DI confirmed faults: fixed addresses, independent of input polarity. */\n'
             '#define FireFaultLatchDisp Parameter[960]\n'
             '#define ValveLinkFaultLatchDisp Parameter[962]\n'
             '#define LeakFaultLatchDisp Parameter[964]\n'
             '#define MainHeatFaultLatchDisp Parameter[966]')],
        'PSC330RK-V10-内机/User/UserSrc/ErrorCheck.c': [
            ('fireValveFlag=0;\n        if(!HeatFaultX6)',
             'fireValveFlag=0;\n'
             '        /* Follow the aggregate latch reset exactly; active inputs reassert below. */\n'
             '        FireFaultLatchDisp=0;\n'
             '        ValveLinkFaultLatchDisp=0;\n'
             '        LeakFaultLatchDisp=0;\n'
             '        if(!HeatFaultX6)'),
            ('\tif(FireAlarmX1 || ValveLinkX4 || LeakProtectX13)fireValveFlag=1;',
             '\t/* Diagnostic latches consume the SAME polarity-adjusted, filtered inputs.\n'
             '\t   They never participate in control: retain the existing aggregate path. */\n'
             '\tif(FireAlarmX1)FireFaultLatchDisp=1;\n'
             '\tif(ValveLinkX4)ValveLinkFaultLatchDisp=1;\n'
             '\tif(LeakProtectX13)LeakFaultLatchDisp=1;\n'
             '\tif(FireAlarmX1 || ValveLinkX4 || LeakProtectX13)fireValveFlag=1;')]
    }
    staged = {}
    for name, pairs in changes.items():
        before = (R/name).read_bytes()
        after = before
        nl = '\r\n' if b'\r\n' in before else '\n'
        for old, new in pairs:
            a, b = (s.replace('\n', nl).encode('ascii') for s in (old, new))
            assert after.count(a) == 1, (name, a)
            after = after.replace(a, b)
        staged[name] = before, after
    OUT.mkdir()
    DAY.mkdir(parents=True, exist_ok=True)
    (OUT/'source_before.json').write_text(json.dumps(inventory(), indent=2), 'utf8')
    diff = []
    for name, (before, after) in staged.items():
        backup = OUT/'source_backup'/name
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(before)
        (R/name).write_bytes(after)
        diff.extend(difflib.unified_diff(before.decode('gb18030', errors='replace').splitlines(True),
            after.decode('gb18030', errors='replace').splitlines(True),
            fromfile=name+' V10.75', tofile=name+' V10.76'))
    (DAY/'source_changes.diff').write_text(''.join(diff).replace('\r\n', '\n'), 'utf8')
    (OUT/'source_after.json').write_text(json.dumps(inventory(), indent=2), 'utf8')


def main():
    if not OUT.exists():
        prepare()
    assert inventory() == json.loads((OUT/'source_after.json').read_text('utf8'))
    build.OUT = OUT
    artifacts = build.build(*build.PROJECTS[0][:-1], '10.76', False, incremental=True)
    manifest = dict(versions={'330':'10.76', '316':'12.56'}, profile='PRODUCTION',
        artifacts=artifacts, source_inventory=inventory(), flashed=False, hardware_tested=False,
        scope='Diagnostic-only fire960, valve962, leak964; existing control and reset preserved')
    (OUT/'PRODUCTION/manifest.json').write_text(json.dumps(manifest, indent=2), 'utf8')
    print('BUILD PASS 330 V10.76; 0 errors, 0 warnings', flush=True)


if __name__ == '__main__':
    main()
