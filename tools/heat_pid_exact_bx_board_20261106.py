"""Visit exact BX boundaries using ordinary gains and legal NTC calibration.

Demand, history, counters and outputs are only read. Parameter changes direct
the next real integral scan; every expected increment is independently checked.
Run exclusively after the main heat/PID/output batches release COM6.
"""
from heat_pid_board_20261106 import *


def run_exact(family):
    b = HeatBench('pid_exact_' + family)
    reader = None
    entry = {'family': family, 'ticks': [], 'required_before': [100, 101, 200, 201, 400, 401, 500, 501]}
    reg = 350 if family == 'preheat' else 347
    ch = 3 if family == 'preheat' else 0
    target = 100 if family == 'preheat' else 250
    cid = {'main': 'T11-021', 'reheat': 'T11-021', 'auxiliary': 'T11-021', 'preheat': 'T11-029'}[family]
    try:
        b.setup(0 if family == 'reheat' else 1)
        b.config({125: 0, 126: 0, 127: int(family in ('reheat', 'auxiliary')),
                  128: 0 if family in ('reheat', 'preheat') else 1 if family == 'auxiliary' else 2,
                  129: 0 if family == 'reheat' else 1,
                  332: int(family in ('reheat', 'auxiliary')), 333: int(family == 'preheat'),
                  334: 0, 315: 0, 160: 250, 161: 250, 346: 0,
                  374: int(family == 'preheat'), 375: 100, 376: 20, 120: 20,
                  412: 1, reg: 1, reg + 1: 1000, reg + 2: 0,
                  329: 2, 330: 0, 331: 0})
        if family == 'auxiliary':
            b.config({315: 1, 327: 1, 318: 0, 319: 120, 12: 500})
        b.temperature(2, 0 if family == 'auxiliary' else 50)
        b.temperature(ch, target - 10)
        reader = PidReader(b, family)
        b.start()
        if family == 'auxiliary':
            entry['full_load_precondition'] = b.wait('exact BX auxiliary full load',
                lambda s: all(x == 3 for pair in s['outdoor_status'] for x in pair), 170)
        # A disabled output selection resets history by normal firmware logic.
        output_reg = 333 if family == 'preheat' else 332 if family in ('reheat', 'auxiliary') else 128
        output_value = b.rd(output_reg)[0]
        b.config({output_reg: 0})
        time.sleep(.2)
        b.config({output_reg: output_value})
        warm = reader.phase('exact_BX_warm_history', 4, 1, 1000, 0, 1, 20)
        assert warm['passed'], warm
        prior = reader.read()
        assert prior['n'] == 0 and prior['valid'] == 2 and prior['history'] == [10, 10, 10], prior
        # With E=1C and T=1s, kp*BX/Ti gives the normalised increment.
        # These settings make the target values reachable in real scans.
        route = [(100, 100, 1), (101, 1, 1), (199, 49, 1), (200, 1, 2), (201, 1, 2),
                 (397, 49, 1)]
        route += [(n, 1, 4) for n in range(398, 402)]
        route += [(497, 16, 1)]
        route += [(n, 1, 6) for n in range(498, 502)]
        route += [(511, 1, 1)]
        for wanted, kp, ti in route:
            before = reader.read()
            assert before['count'] <= 6, ('insufficient time to change next scan parameters', before)
            b.config({reg: kp, reg + 1: ti})
            configured = reader.read()
            assert all(before[k] == configured[k] for k in ('n', 'valid', 'residual', 'history')), \
                ('scan occurred while changing parameters', before, configured)
            began = time.monotonic()
            last = configured
            while True:
                after = reader.read()
                if (after['count'] < last['count'] or
                    any(after[k] != last[k] for k in ('n', 'valid', 'residual', 'history'))):
                    break
                assert time.monotonic() - began < 2, 'next real PID scan missing'
                last = after
                time.sleep(.015)
            expected = expected_step(before, 10, kp, ti, 0, 1, 20)
            out = b.sample_heat('exact BX ' + str(before['n']) + ' -> ' + str(wanted))
            channel = 1 if family == 'preheat' else 9 if family == 'reheat' else 0
            z = signed16(b.rd(930 if family == 'preheat' else 928)[0])
            tick = {'before': before, 'after': after, 'parameters': {'kp': kp, 'ti': ti, 'T': 1},
                    'expected': expected, 'wanted': wanted, 'actual_z': z, 'output': out}
            tick['passed'] = (after['n'] == wanted and out['ao'][channel] == wanted and z == expected['z'] and
                              all(after[k] == expected[k] for k in ('n', 'valid', 'residual', 'history')))
            entry['ticks'].append(tick)
            b.log['exact_bx'] = entry
            b.save()
            print('EXACT BX', family, before['n'], '->', after['n'], 'BX', expected['bx'], tick['passed'], flush=True)
            assert tick['passed'], tick
        seen = {t['before']['n'] for t in entry['ticks']}
        entry['exact_boundary_coverage'] = {n: n in seen for n in entry['required_before']}
        entry['passed'] = all(entry['exact_boundary_coverage'].values()) and all(t['passed'] for t in entry['ticks'])
        if family == 'auxiliary':
            entry['loaded_auxiliary_before_unload'] = out
            assert out['heat'] == 511 and out['ao'][0] == 511, out
            b.temperature(2, 60)
            entry['nonfull_shutdown'] = b.wait('exact BX loaded auxiliary must close on nonfull',
                lambda s: any(x != 3 for pair in s['outdoor_status'] for x in pair)
                and s['ao'][0] == 0 and b.rd(890)[0] == 0, 100)
            entry['nonfull_hold'] = b.observe('auxiliary 51.1 percent to zero hold', 4)
            assert all(s['ao'][0] == 0 and s['diag'][18] == 0 for s in entry['nonfull_hold'])
        # Keep each family separate. This supplements rather than overwrites
        # the shared thermal PID matrix entry used by the older script.
        b.log['exact_bx'] = entry
        b.save()
        text = (f'{family}真实扫描前需求100/101/200/201/400/401/500/501全部覆盖；'
                f'{len(entry["ticks"])}次增量、BX及AO逐拍符合；未写PID状态。')
        with (R / '制热曲线_PID_板上续测_20261106.md').open('a', encoding='utf8') as f:
            f.write(f'\n- [x] **{cid} {family} 精确BX边界补测（软件回读）**：{text} '
                    f'[原始证据]({b.path.relative_to(R).as_posix()})\n')
        print('EXACT COMPLETE', text, flush=True)
    except Exception:
        entry['error'] = traceback.format_exc()
        b.log['exact_bx'] = entry
        b.save()
        raise
    finally:
        if reader:
            reader.close()
        b.finish()
        print('EXACT RESTORED', family, b.log.get('restored'), b.path, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--families', nargs='+', default=['main', 'reheat', 'auxiliary', 'preheat'])
    for family in p.parse_args().families:
        run_exact(family)
