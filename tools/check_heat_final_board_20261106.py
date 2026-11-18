"""Independent read-only final check after every serial test writer exits."""
import os
os.environ.setdefault('PSC_BENCH_PACKAGE', '.codex-tmp/preheat_stage_display_v1053_v1239_20261106')
os.environ.setdefault('PSC_BENCH_INDOOR_VERSION', '10.53')
from heat_dynamic_board_20261106 import *
from run_indoor_bench_20261105 import client, snap


def main():
    paths = sorted(D.glob('remaining571_heat_dynamic_*_20261106_*.json'))
    batches = [(p, json.loads(p.read_text('utf8'))) for p in paths]
    completed = [(p, d) for p, d in batches if d.get('restored') is True]
    current = [(p, d) for p, d in completed if 'error' not in d and not d.get('cleanup_error')]
    assert len(current) >= 10, 'Inspect missing or unfinished curve/PID/parallel/exact batches'
    earliest = min(current, key=lambda pair: pair[1]['started'])[1]
    before = earliest['full_configuration_before']
    touched = {a for _, d in current for a in d.get('original', {})}
    report = {'at': now(), 'read_only': True, 'batches': [p.relative_to(R).as_posix() for p, _ in current],
              'configuration_reference_started': earliest['started'], 'snapshots': []}
    c = client()
    try:
        report['versions'] = c.read_holding_registers(1, 2622, 18)
        assert report['versions'] == runtime.EXPECTED, report['versions']
        report['profiles'] = c.read_holding_registers(1, 1298, 2)
        assert report['profiles'][1] == 15107, report['profiles']
        report['config_readback'] = {}
        for a, n in [(0, 125), (125, 125), (250, 125), (375, 125), (1229, 60)]:
            report['config_readback'].update({str(a + i): v for i, v in enumerate(c.read_holding_registers(1, a, n))})
        report['configuration_mismatches'] = {
            a: {'before': before[a], 'after': report['config_readback'][a]}
            for a in touched & before.keys() & report['config_readback'].keys()
            if a != '398' and before[a] != report['config_readback'][a]}
        for _ in range(2):
            s = snap(c)
            report['snapshots'].append(s)
            assert s['state'][9] == 0 and loads_off(s), s
            assert not any(s['faults']), s
            assert all(x == 0 for pair in s['outdoor_status'] for x in pair), s
            time.sleep(.5)
        report['temperatures_510_513'] = [signed16(x) for x in c.read_holding_registers(1, 510, 4)]
        report['ntc_calibrations_492_495'] = [signed16(x) for x in c.read_holding_registers(1, 492, 4)]
        assert not report['configuration_mismatches'], report['configuration_mismatches']
        report['passed'] = True
    finally:
        c.close()
        dump(D / 'heat_final_independent_readback_20261106.json', report)
    print(json.dumps({k: report[k] for k in ('passed', 'versions', 'configuration_mismatches',
                                            'temperatures_510_513', 'ntc_calibrations_492_495')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
