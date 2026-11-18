"""Live compressor/humidity PID: legal configuration, read-only SWD state.

No output/demand/history/counter writes. Original CSV is left untouched because
the desktop currently presents an enterprise-encrypted rather than text file.
"""
import os
os.environ.setdefault('PSC_BENCH_PACKAGE', '.codex-tmp/preheat_stage_display_v1053_v1239_20261106')
os.environ.setdefault('PSC_BENCH_INDOOR_VERSION', '10.53')
from heat_pid_board_20261106 import *


def ai_exact(b, value):
    """Engineering-map input simulation; verify the actual AI1 quantity."""
    center = value-getattr(b, '_humidity_mapping_bias', 0)
    for _ in range(4):
        b.ai(1, center)
        actual = b.rd(501)[0]
        b._humidity_mapping_bias = actual-center
        b.log.setdefault('humidity_input_precision', []).append(dict(requested=value, center=center, actual=actual))
        b.save()
        if actual == value: return actual
        center += value-actual
    raise AssertionError(('AI1 engineering-map precision', value, actual))


class Reader:
    def __init__(self, b, family):
        self.b, self.family = b, family
        self.comp = family in ('cool', 'heatpump')
        fn = 'SysNergryAction_PID' if self.comp else 'HumidtCtrl'
        names = ({'n': 'nCool1000', 'history': 'eCool', 'valid': 'coolCnt', 'residual': 'coolResidualMilli',
                  'count': 'pidCount', 'sign': 'lastZCool'} if family == 'cool' else
                 {'n': 'nHeat1000', 'history': 'eHeat', 'valid': 'heatCnt', 'residual': 'heatResidualMilli',
                  'count': 'pidCount', 'sign': 'lastZHeat'} if self.comp else
                 {'n': 'demand', 'history': 'hist', 'valid': 'validSamples', 'residual': 'residualMilli', 'count': 'count'})
        sys.path.insert(0, str(R / '.codex-tmp/defrost_test_deps'))
        from elftools.elf.elffile import ELFFile
        found = {}
        with (I / (BOARDS[2][-1] + '.axf')).open('rb') as f:
            di = ELFFile(f).get_dwarf_info()
            for cu in di.iter_CUs():
                for die in cu.iter_DIEs():
                    name = die.attributes.get('DW_AT_name')
                    if die.tag != 'DW_TAG_subprogram' or not name or name.value.decode() != fn:
                        continue
                    for v in die.iter_children():
                        name, loc = v.attributes.get('DW_AT_name'), v.attributes.get('DW_AT_location')
                        if name and loc and isinstance(loc.value, list) and len(loc.value) == 5 and loc.value[0] == 3:
                            found[name.value.decode()] = int.from_bytes(bytes(loc.value[1:]), 'little')
        self.addr = {k: found[v] for k, v in names.items()}
        self.width = dict(n=4, history=12, valid=1, residual=8, count=4, sign=4)
        # The linker places zero-initialised history ~6KB away from the small
        # scalar state. Read those blocks separately; sweeping the intervening
        # RAM is slow enough to cross multiple scheduler ticks over SWD.
        self.base = min(a for k, a in self.addr.items() if k != 'history')
        self.end = max(a + self.width[k] for k, a in self.addr.items() if k != 'history')
        self.session = ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1], target_override=BOARDS[2][2],
            options={'connect_mode': 'attach', 'resume_on_disconnect': True, 'frequency': 1000000})
        self.session.open()
        self.t = self.session.target
        b.log['live_symbols'] = {'function': fn, 'fields': self.addr}
        b.save()

    def close(self):
        self.session.close()

    def read(self):
        for _ in range(15):
            raw = bytes(self.t.read_memory_block8(self.base, self.end - self.base))
            value = lambda k, fmt: struct.unpack_from(fmt, raw, self.addr[k] - self.base)
            history = list(struct.unpack('<3i', bytes(self.t.read_memory_block8(self.addr['history'], 12))))
            s = {'n': value('n', '<i')[0], 'count': value('count', '<I')[0], 'valid': value('valid', '<B')[0],
                 'history': history, 'residual': value('residual', '<q')[0]}
            if self.comp:
                s['sign'] = value('sign', '<i')[0]
            if (s['count'] == self.t.read32(self.addr['count']) and
                (s['n'] & 0xffffffff) == self.t.read32(self.addr['n']) and
                s['history'] == list(struct.unpack('<3i', bytes(self.t.read_memory_block8(self.addr['history'], 12))))):
                s['t'] = time.monotonic()
                return s
        raise AssertionError('No coherent live PID state')

    def oracle(self, before, error, kp, ti, td, T, width, ys):
        if not self.comp:
            return expected_step(before, error, kp, ti, td, T, width)
        if before['valid'] < 2:
            n = 0 if error <= 5 else 200 if error <= 20 else 300 if error <= 40 else 400 if error <= 50 else 500
            return dict(n=n, history=[error] + before['history'][:2], valid=before['valid'] + 1,
                        residual=0, z=0, sign=int(n > 0), bx=None)
        adjusted = dict(before)
        # Independent exact rational specification formula; YS only adjusts
        # the current error, never the stored previous error samples.
        h = [error] + before['history'][:2]
        if abs(error) * 4 < width and ys == 0:
            return dict(n=before['n'], history=h, valid=before['valid'], residual=0, z=0, sign=0, bx=None)
        n = before['n']
        bx = F(1, 10) if n <= 100 else F(1, 5) if n <= 200 else F(2, 5) if n <= 400 else F(3, 5) if n <= 500 else F(1)
        expr = F(error + ys - h[1]) + F(T, ti) * (error + ys) + F(td, T) * (error + ys - 2*h[1] + h[2])
        acc = before['residual'] + trunc(1000 * kp * bx * expr)
        z = trunc(F(acc, 1000))
        n = max(0, min(1000, n + z))
        res = acc - z * 1000
        if (n == 0 and acc < 0) or (n == 1000 and acc > 0):
            res = 0
        return dict(n=n, history=h, valid=before['valid'], residual=res, z=z,
                    sign=(acc > 0) - (acc < 0), bx=str(bx))

    def phase(self, label, seconds, kp=10, ti=1, td=0, T=1, width=20):
        b = self.b
        reg = 416 if self.family == 'cool' else 426 if self.comp else 353
        b.config({reg: kp, reg+1: ti, reg+2: td, 412: T, 120 if self.comp else 361: width})
        phase = dict(label=label, seconds_requested=seconds, parameters=dict(kp=kp, ti=ti, td=td, T=T, width=width),
                     ticks=[], missed_scan_gaps=[], sampling_pauses=[])
        before = self.read()
        started = time.monotonic()
        previous_tick = None
        while time.monotonic() - started < seconds:
            s = self.read()
            if s['count'] < before['count'] or any(s[k] != before[k] for k in ('n', 'valid', 'history', 'residual')):
                if s['t'] - before['t'] > T * .85:
                    # An acquisition pause need not lose a scan. The actual
                    # 100ms firmware counter disambiguates one observed wrap
                    # from skipped complete cycles. Preserve every pause.
                    scans = round((s['t']-before['t'] + (before['count']-s['count'])/10) / T)
                    pause = {'before': before, 'after': s, 'estimated_scan_edges': scans}
                    phase['sampling_pauses'].append(pause)
                    if scans != 1:
                        phase['missed_scan_gaps'].append(pause)
                display = b.rd(872, 10) if self.comp else b.rd(931, 9)
                ys = signed16(display[5]) if self.family == 'cool' else 0
                expected = self.oracle(before, s['history'][0], kp, ti, td, T, width, ys)
                fields = ('n', 'valid', 'history', 'residual', 'sign') if self.comp else ('n', 'valid', 'history', 'residual')
                formula = all(s[k] == expected[k] for k in fields)
                z = signed16(display[7] if self.comp else display[8])
                formula &= z == max(-32768, min(32767, expected['z']))
                out = b.snapshot(label)
                output_ok = (display[8] == s['n'] and b.rd(115)[0] == s['n']) if self.comp else out['ao'][2] == s['n'] and out['do'][11] == 0
                count_check = None
                if self.comp:
                    target, actual, cn = b.rd(881)[0], b.rd(119)[0], b.rd(2678)[0]
                    sign = s['sign']
                    want = (max(1, (cn*s['n']+999)//1000) if sign > 0 else cn*s['n']//1000 if sign < 0 else actual)
                    count_check = dict(target=target, actual=actual, installed=cn, expected=want,
                                       matched=target == want, sign=sign)
                    output_ok &= count_check['matched']
                edge = s['t'] - s['count']/10
                tick = dict(before=before, after=s, expected=expected, ys=ys, actual_z=z,
                            formula_matches=bool(formula), output_matches=bool(output_ok), output=out,
                            count_check=count_check, observed_edge_s=edge,
                            observed_period_s=None if previous_tick is None else edge-previous_tick)
                phase['ticks'].append(tick)
                previous_tick = edge
                print('LIVE PID', self.family, label, 'N', s['n'], 'E', s['history'][0], 'Z', z,
                      'formula', bool(formula), 'output', bool(output_ok), flush=True)
            before = s
            time.sleep(.025)
        phase['passed'] = bool(phase['ticks']) and not phase['missed_scan_gaps'] and all(t['formula_matches'] and t['output_matches'] for t in phase['ticks'])
        b.log.setdefault('pid_phases', []).append(phase)
        b.save()
        return phase


def run(family):
    b = HeatBench('remaining_pid_' + family)
    reader = None
    comp = family != 'humidity'
    first = 1 if family == 'cool' else 9 if comp else 33
    reg = 416 if family == 'cool' else 426 if comp else 353
    try:
        b.setup(0 if family == 'cool' else 1)
        b.config({315: 0, 128: 1 if comp else 0, 127: 0, 332: 0, 333: 0,
                  125: 0, 126: 0 if comp else 1, 248: 0 if comp else 1, 334: 0 if comp else 1,
                  168: 0, 160: 250, 161: 250, 162: 500, 361: 200,
                  412: 1, 120: 20, reg: 10 if comp else 1, reg+1: 1, reg+2: 0,
                  329: 2, 330: 0, 331: 0, 346: 0, 320: 0, 30: 0, 12: 500})
        b.temperature(2, 50)
        b.temperature(0, 260 if family == 'cool' else 240 if comp else 250)
        if not comp:
            ai_exact(b, 400)
        reader = Reader(b, family)
        b.start()
        phases = []
        def phase(label, seconds, **kw):
            if not comp:
                kw.setdefault('kp', 1)
                kw.setdefault('width', 200)
            p = reader.phase(label, seconds, **kw)
            phases.append(p)
            return p
        def error(value):
            if comp:
                b.temperature(0, 250+value if family == 'cool' else 250-value)
            else:
                ai_exact(b, 500-value)
        positive = phase('positive_ramp_and_initial_history', 42)
        ticks = positive['ticks']
        init = ticks[:2]
        b.record_local(f'T11-{first:03d}', positive['passed'] and len(init) == 2 and all(t['after']['valid'] <= 2 and t['after']['n'] == (200 if comp else 0) for t in init),
                       f'{family}首次两样本及后续真实扫描，{len(ticks)}拍；按规格初始开度与公式逐拍核对。', {'phases': [positive]})
        b.record_local(f'T11-{first+1:03d}', positive['passed'] and max(t['after']['n'] for t in ticks) == 1000,
                       f'{family}正误差动态加载至1000，公式、输出及目标台数同步核对。', {'phases': [positive]})
        error(-10 if comp else -100)
        negative = phase('negative_unload', 38)
        b.record_local(f'T11-{first+2:03d}', negative['passed'] and negative['ticks'][-1]['after']['n'] == 0,
                       f'{family}负误差实际卸载至0，{len(negative["ticks"])}拍。', {'phases': [negative]})
        error(10 if comp else 100)
        prepare = phase('prepare_nonsaturated', 20, kp=5 if comp else 1, ti=1 if comp else 2)
        boundaries = []
        for e in ((0, 9, -9, 10, -10) if comp else (0, 99, -99, 100, -100)):
            error(e)
            boundaries.append(phase('deadband_' + str(e), 4, kp=5 if comp else 1, ti=100, width=40 if comp else 400))
        b.record_local(f'T11-{first+3:03d}', all(p['passed'] for p in boundaries),
                       f'{family}严格死区边界：'+('E=0/±0.9/±1.0℃，幅差4.0℃。' if comp else 'E=0/±9.9/±10.0%RH，幅差40.0%RH；AI1工程映射软件模拟。'), {'phases': boundaries})
        derivative = []
        for e in ((10, 20, -10, 0, 10) if comp else (100, 200, -100, 0, 100)):
            error(e)
            derivative.append(phase('derivative_' + str(e), 4, kp=13 if comp else 1, ti=41, td=7))
        b.record_local(f'T11-{first+5:03d}', all(p['passed'] for p in derivative),
                       f'{family}Kp{13 if comp else 1}/Ti41/Td7非零微分，正负及零误差真实扫描。', {'phases': derivative})
        timing = []
        for period in (1, 5, 10):
            error(10 if comp else 100)
            timing.append(phase('scan_' + str(period), period*3+1, kp=1, ti=100, T=period))
        timing_ok = all(p['passed'] and all(abs(t['observed_period_s']-p['parameters']['T']) < .25
            for t in p['ticks'] if t['observed_period_s'] is not None) for p in timing)
        b.record_local(f'T11-{first+6:03d}', timing_ok,
                       f'{family}T=1/5/10秒真实扫描周期完成；没有改写计时器。', {'phases': timing})
        all_ticks = [t for p in phases for t in p['ticks']]
        bx = sorted({t['expected']['bx'] for t in all_ticks if t['expected']['bx']})
        exact = {x: any(t['before']['n'] == x for t in all_ticks) for x in (100, 101, 200, 201, 400, 401, 500, 501)}
        b.record_local(f'T11-{first+4:03d}', all(p['passed'] for p in phases) and len(bx) == 5,
                       f'{family}实际BX={bx}；精确需求边界覆盖={exact}，未覆盖点仍待补。',
                       {'phases': phases, 'exact_boundary_coverage': exact})
        b.record_local(f'T11-{first+7:03d}', positive['passed'] and negative['passed'] and prepare['passed'] and
                       any(t['after']['n'] == 1000 for t in ticks) and any(t['after']['n'] == 0 for t in negative['ticks']),
                       f'{family}上下限保持及反向退出，真实扫描余数、需求和软件输出符合。', {'phases': [positive, negative, prepare]})
        b.log['all_pid_phases_passed'] = all(p['passed'] for p in phases)
        assert b.log['all_pid_phases_passed'], 'Inspect retained formula/output mismatches'
    except Exception:
        b.log['error'] = traceback.format_exc()
        b.save()
        raise
    finally:
        if reader:
            reader.close()
        b.finish()
        print('LIVE PID RESTORED', family, b.log.get('restored'), b.path, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--families', nargs='+', default=['cool', 'heatpump', 'humidity'])
    for family in p.parse_args().families:
        run(family)
