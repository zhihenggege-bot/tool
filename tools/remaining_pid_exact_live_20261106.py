"""Exact compressor and humidity BX boundaries using real integral scans."""
from remaining_pid_live_20261106 import *


def run_exact(family):
    b = HeatBench('remaining_exact_' + family)
    reader = None
    comp = family != 'humidity'
    reg = 416 if family == 'cool' else 426 if comp else 353
    width = 20 if comp else 200
    error = 10 if comp else 100
    required = [100, 101, 200, 201, 400, 401, 500, 501]
    entry = {'family': family, 'ticks': [], 'required_before': required,
             'stimulus': '合法NTC校准' if comp else 'AI1工程映射模拟，非物理湿度信号源'}
    try:
        b.setup(0 if family == 'cool' else 1)
        b.config({315: 0, 327: 1, 128: 1 if comp else 0, 127: 0,
                  332: 0, 333: 0, 125: 0, 126: 0 if comp else 1,
                  248: 0 if comp else 1, 334: 0 if comp else 1, 168: 0,
                  160: 250, 161: 250, 162: 500, 361: 200, 120: 20,
                  412: 1, reg: 1, reg+1: 1000, reg+2: 0,
                  329: 2, 330: 0, 331: 0, 346: 0, 320: 0, 30: 0, 12: 500})
        # Fresh-air temperature is not the control input for these indoor PID
        # cases; leave NTC2 available for the operator's next fixture setting.
        b.temperature(0, 255 if family == 'cool' else 245 if comp else 250)
        if not comp: ai_exact(b, 400)
        reader = Reader(b, family)
        b.start()
        warm = reader.phase('warm_initial_zero', 4, kp=1, ti=1000, width=width)
        assert warm['passed']
        if comp:
            b.temperature(0, 260 if family == 'cool' else 240)
            warm2 = reader.phase('warm_E1_without_output_jump', 3, kp=1, ti=1000)
            assert warm2['passed']
        state = reader.read()
        assert state['n'] == 0 and state['valid'] == 2 and state['history'] == [error]*3, state
        route = [(100, 100, 1), (101, 1, 1), (199, 49, 1), (200, 1, 2), (201, 1, 2), (397, 49, 1)]
        route += [(n, 1, 4) for n in range(398, 402)]
        route += [(497, 16, 1)]
        route += [(n, 1, 6) for n in range(498, 502)]
        route += [(511, 1, 1)]
        for wanted, kp, ti in route:
            if not comp: ti *= 10
            before = reader.read()
            assert before['count'] <= 6, ('time needed before next scan', before)
            b.config({reg: kp, reg+1: ti})
            configured = reader.read()
            assert all(before[k] == configured[k] for k in ('n', 'valid', 'residual', 'history'))
            began = time.monotonic()
            last = configured
            while True:
                after = reader.read()
                if after['count'] < last['count'] or any(after[k] != last[k] for k in ('n', 'valid', 'history', 'residual')): break
                assert time.monotonic()-began < 2
                last = after
                time.sleep(.015)
            expected = reader.oracle(before, error, kp, ti, 0, 1, width, 0)
            fields = ('n', 'valid', 'residual', 'history', 'sign') if comp else ('n', 'valid', 'residual', 'history')
            display = b.rd(872, 10) if comp else b.rd(931, 9)
            z = signed16(display[7] if comp else display[8])
            out = b.snapshot('exact BX')
            output_ok = display[8] == wanted and b.rd(115)[0] == wanted if comp else out['ao'][2] == wanted
            tick = dict(before=before, after=after, parameters=dict(kp=kp, ti=ti, T=1), expected=expected,
                        actual_z=z, output=out, wanted=wanted)
            tick['passed'] = after['n'] == wanted and output_ok and z == expected['z'] and all(after[k] == expected[k] for k in fields)
            entry['ticks'].append(tick)
            b.log['exact_bx'] = entry
            b.save()
            print('REMAINING EXACT', family, before['n'], after['n'], expected['bx'], tick['passed'], flush=True)
            assert tick['passed'], tick
        seen = {t['before']['n'] for t in entry['ticks']}
        entry['exact_boundary_coverage'] = {n: n in seen for n in required}
        entry['passed'] = all(entry['exact_boundary_coverage'].values())
        cid = {'cool': 'T11-005', 'heatpump': 'T11-013', 'humidity': 'T11-037'}[family]
        b.record_local(cid, entry['passed'],
            f'{family}真实扫描前N=100/101/200/201/400/401/500/501全部覆盖，'
            f'{len(entry["ticks"])}次公式、余数、BX及软件输出匹配；不写PID/需求/输出RAM；'+entry['stimulus']+'。', entry)
    except Exception:
        b.log['error'] = traceback.format_exc()
        b.save()
        raise
    finally:
        if reader: reader.close()
        b.finish()
        print('REMAINING EXACT RESTORED', family, b.log.get('restored'), b.path, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--families', nargs='+', default=['cool', 'heatpump', 'humidity'])
    for family in p.parse_args().families: run_exact(family)
