"""Execute actual Keil ARM code for the four 2026-11-10 fixes; no hardware IO.

Records fixture inputs, observed outputs, artifact hashes and individual verdicts.
Use --package/--old to reproduce the same checks on the previous release.
"""
import argparse
import hashlib
import json
from pathlib import Path

import test_defrost_lifecycle_arm as lifecycle
import audit_outdoor_spec_20261109 as audit

ROOT = lifecycle.ROOT
RESULTS = []


def check(label, got, want):
    row = dict(id=label, observed=got, expected=want, passed=got == want)
    RESULTS.append(row)
    print(('PASS ' if row['passed'] else 'FAIL ') + label, got, flush=True)


def setup_paths(package, profile, old):
    ov, iv = ('12.39', '10.55') if old else ('12.40', '10.56')
    audit.OUT = lifecycle.OUT = package / profile / f'PSC316_V{ov}_{profile}.axf'
    lifecycle.IN = package / profile / f'PSC330_V{iv}_{profile}.axf'


def emergency(profile):
    # Covers active, a supplementary compressor not yet started, recovery,
    # pending request and request not yet permitted. All use actual state code.
    for scenario in ('active', 'single', 'one-ended', 'recovery', 'manual-pending', 'auto-pending'):
        f = lifecycle.outdoor(running=(1, int(scenario != 'single')))
        if scenario == 'one-ended':
            f.var('X_00', 1)
            f.call('DefrostProcess')
        if scenario == 'recovery':
            f.var('X_00', 1)
            f.var('X_02', 1)
            f.call('DefrostProcess')
        if scenario in ('manual-pending', 'auto-pending'):
            f = audit.base(1)
            f.p(1410, int(scenario == 'manual-pending'))
            f.p(1409, 0)
            if scenario == 'auto-pending':
                f.p(182, 150)
                f.p(1422, 120)
                f.p(613, 1)
                audit.running(f, 0, 1)
                f.var('DefGapCount', 1800, 1, 4)
            f.call('DefrostProcess')
        check(f'{profile}/abort/{scenario}/fixture-phase',
              f.p(1420 if scenario == 'manual-pending' else 1421),
              7 if scenario == 'recovery' else 5 if scenario == 'manual-pending'
              else 1 if scenario == 'auto-pending' else 8)
        f.var('CompStopTime', 17, 0, 4)
        f.p(1406, 1)
        f.call('DefrostProcess')
        f.call('CompErrAction')
        f.call('IoOutAction')
        got = [f.p(1420), f.p(1421), f.var('PSC316DefrostState')]
        got += [f.var('Comp', index=i, width=1) for i in range(2)]
        got += [f.var('output', index=i, width=1) for i in range(8)]
        check(f'{profile}/abort/{scenario}/immediate', got, [0]*13)
        flags = ('SysHaveDef', 'DefComp0', 'PSC316DefrostEligible',
                 'PSC316DefrostEnded', 'PSC316DefrostStarted',
                 'PSC316DefrostRunTime', 'TimerDefrostMode',
                 'PSC316DefrostRecoverDelay', 'PSC316DefrostWasActive')
        values = []
        for name in flags:
            width = 1 if name in ('PSC316DefrostEligible', 'PSC316DefrostEnded',
                                  'PSC316DefrostStarted') else 4
            values += [f.var(name, index=i, width=width) for i in range(2)]
        check(f'{profile}/abort/{scenario}/flags', values, [0]*len(values))
        check(f'{profile}/abort/{scenario}/stop-counter-preserved',
              f.var('CompStopTime', index=0, width=4), 17)
        for _ in range(3):
            f.p(1410, 1)
            f.p(1409, 1)
            f.call('DefrostProcess')
        check(f'{profile}/abort/{scenario}/held-no-reentry', [f.p(1420), f.p(1421)], [0, 0])
        f.p(1406, 0)
        f.p(1410, 1)
        f.call('DefrostProcess')
        check(f'{profile}/abort/{scenario}/stale-permit-no-reentry',
              [f.p(1420), f.p(1421)], [0, 0])
        f.p(1409, 0)
        f.call('DefrostProcess')
        f.p(1410, 1)
        f.p(1409, 1)
        f.var('X_00', 0)
        f.var('X_02', 0)
        f.call('DefrostProcess')
        # Fresh manual request can be accepted only AFTER permit withdrawal.
        check(f'{profile}/abort/{scenario}/fresh-request', f.p(1420), 8)

    # A normal restart after abort still goes through ModuleCompAction's
    # configured stop time and airflow gate, rather than the manual-defrost path.
    f = lifecycle.outdoor()
    f.p(1406, 1)
    f.call('DefrostProcess')
    f.call('CompErrAction')
    f.call('IoOutAction')
    f.p(1406, 0)
    f.p(1409, 0)
    f.call('DefrostProcess')
    f.p(1400, 1)
    f.p(99, 1)
    f.p(42, 120)
    f.p(45, 0)
    f.var('output', 1, 2, 1)  # real software fan-run output
    f.var('Systick_1ms', 1000)
    f.call('ModuleCompAction')
    f.var('Systick_1ms', 3000)
    f.var('CompStopTime', 119, 0, 4)
    f.call('ModuleCompAction')
    check(f'{profile}/restart/119-of-configured120s', f.var('Comp', index=0, width=1), 0)
    f.var('CompStopTime', 120, 0, 4)
    f.call('ModuleCompAction')
    check(f'{profile}/restart/120-of-configured120s', f.var('Comp', index=0, width=1), 1)

    f = audit.defrost()
    f.p(1406, 1)
    # Same relevant control/output ordering as UserAction and the outer loop.
    for handler in ('ModuleAction', 'DefrostProcess', 'OutdoorUnitAction',
                    'BoardFanControl', 'ErrorProcess', 'IoOutAction',
                    'OutdoorProtectOutputLimit'):
        f.call(handler)
    check(f'{profile}/abort/control-output-order',
          [f.p(1420), f.p(1421)] + [f.var('output', index=n, width=1) for n in range(8)], [0]*10)

    o = lifecycle.outdoor()
    i = lifecycle.indoor()
    i.var('PSC316DefrostOwner', 1)
    i.field(False, 2, 'CanDefrost', value=1)
    lifecycle.feedback(o, i)
    i.p(1406, 1)
    i.call('PSC316UpdateDefrostOwner')
    check(f'{profile}/owner/urgent-revokes-grants',
          [i.field(True, u, 'DefrostSignal', c) for u in range(1, 5) for c in range(2)], [0]*8)
    check(f'{profile}/owner/await-feedback', i.var('PSC316DefrostOwner'), 1)
    o.p(1406, 1)
    o.call('DefrostProcess')
    lifecycle.feedback(o, i)
    i.call('PSC316UpdateDefrostOwner')
    check(f'{profile}/owner/abort-feedback-releases', i.var('PSC316DefrostOwner'), 0)
    i.p(1406, 0)
    i.call('PSC316UpdateDefrostOwner')
    check(f'{profile}/owner/next-unit-after-release', i.var('PSC316DefrostOwner'), 2)


def timed(profile):
    def fixture(temp, threshold=150, gap=1800, fault=True):
        f = audit.base(1)
        f.p(182, threshold)
        f.p(1422, temp)
        f.p(613, int(fault))
        audit.running(f, 0, 1)
        f.var('DefGapCount', gap, 1, 4)
        # Deliberately no minimum normal runtime, no cold fin, no temperature
        # difference and no second pulses: timed must not inherit those gates.
        f.var('CompRunTime', 0, 1, 4)
        f.var('FinTemp', 500, 1, 2)
        return f
    for threshold in (50, 100, 150):
        for delta, want in ((-1, 1), (0, 0), (1, 0)):
            f = fixture(threshold+delta, threshold)
            f.call('DefEnable')
            check(f'{profile}/timed/threshold{threshold}/delta{delta}/no60s',
                  f.var('DefComp0', index=1, width=4), want)
    for gap, want in ((1799, 0), (1800, 1)):
        f = fixture(120, gap=gap)
        f.call('DefEnable')
        check(f'{profile}/timed/interval{gap}', f.var('DefComp0', index=1, width=4), want)
    f = fixture(120, fault=False)
    f.var('uc1s', 1)
    for _ in range(61):
        f.call('DefEnable')
    check(f'{profile}/normal/12C-even-with-setting15', f.var('DefComp0', index=1, width=4), 0)
    f = fixture(90, fault=False)
    f.var('CompRunTime', 600, 1, 4)
    f.var('FinTemp', -30, 1, 2)
    f.var('uc1s', 1)
    for _ in range(59):
        f.call('DefEnable')
    check(f'{profile}/normal/before60s', f.var('DefComp0', index=1, width=4), 0)
    f.call('DefEnable')
    check(f'{profile}/normal/at60s', f.var('DefComp0', index=1, width=4), 1)
    f = fixture(100, fault=False)
    f.var('CompRunTime', 600, 1, 4)
    f.var('FinTemp', -30, 1, 2)
    f.var('uc1s', 1)
    for _ in range(61):
        f.call('DefEnable')
    check(f'{profile}/normal/equal10C', f.var('DefComp0', index=1, width=4), 0)
    for temp, seconds in ((39, 240), (40, 240), (50, 240), (60, 240), (61, 180)):
        f = fixture(temp)
        check(f'{profile}/timed/duration{temp}/existing-gap-policy',
              f.call('PSC316TimedDefrostSeconds'), seconds)


def fans(profile):
    for mode in (0, 1):
        for unit, fan in ((0, 0), (0, 1), (1, 2), (1, 3), (2, 2), (2, 4)):
            for wrap in (False, True):
                f = audit.base(mode, unit, fan)
                # Set legal high/low pressure capabilities for the configuration.
                f.p(107, 1)
                # Establish actual physical on -> off edges, with timers updated
                # on those edges, as in BoardFanControl. 30 seconds is configured
                # even for BENCH: that profile scales action spacing, not min stop.
                start = (2**32-15000) if wrap else 1000
                for address in (872, 874):
                    f.p(address, 1)
                f.var('Systick_1ms', start)
                f.var('uc1s', 1)
                f.call('OutdoorFanUpdateTimers')
                for address in (872, 874):
                    f.p(address, 0)
                stopped = start+30000
                f.var('Systick_1ms', stopped)
                f.call('OutdoorFanUpdateTimers')
                # Prestart and heating steady state are both exercised. For
                # type0 the two contact bits describe ONE physical fan.
                early = []
                for ms in (1, 1000, 4000, 15000, 29000, 29999):
                    f.var('Systick_1ms', stopped+ms)
                    f.var('uc1s', 0)
                    # Real second counters, alongside the real edge timer.
                    for n in range(2):
                        f.var('OutdoorFanStopSeconds', ms//1000, n, 4)
                    f.var('OutdoorFanChangeSeconds', ms//1000)
                    f.call('OutdoorFanPrestart')
                    if mode:
                        f.call('OutdoorFanHeatPump')
                    early.append(int(bool(f.p(872) or f.p(874))))
                label = f'{profile}/fan/mode{mode}/{unit}-{fan}/wrap{int(wrap)}'
                check(label+'/before30s', early, [0]*len(early))
                f.var('Systick_1ms', stopped+30000)
                for n in range(2):
                    f.var('OutdoorFanStopSeconds', 30, n, 4)
                f.var('OutdoorFanChangeSeconds', 30)
                f.call('OutdoorFanPrestart')
                check(label+'/at30s', int(bool(f.p(872) or f.p(874))), 1)


def fan_scans(profile):
    # Run the public fan scan, including handover into the steady controller,
    # with either neither compressor running or one running/one pending.
    for mode in (0, 1):
        for unit, fan in ((0, 0), (0, 1), (1, 2), (1, 3), (2, 2), (2, 4)):
            for already in (0, 1):
                f = audit.base(mode, unit, fan)
                f.call('BoardFanControl')  # consume first configuration change
                for a in (872, 874):
                    f.p(a, 1)
                f.var('Systick_1ms', 1000)
                f.var('uc1s', 1)
                f.call('OutdoorFanUpdateTimers')
                for a in (872, 874):
                    f.p(a, 0)
                f.var('Systick_1ms', 31000)
                f.var('uc1s', 0)
                f.call('OutdoorFanUpdateTimers')
                f.p(1400, 1)
                f.p(1403, 1)
                audit.running(f, already, 0)
                early = []
                for sec in range(1, 30):
                    f.var('Systick_1ms', 31000+sec*1000)
                    f.var('uc1s', 1)
                    f.call('BoardFanControl')
                    early.append(int(bool(f.p(872) or f.p(874))))
                label = f'{profile}/scan/mode{mode}/{unit}-{fan}/running{already}'
                check(label+'/before30s', sum(early), 0)
                f.var('Systick_1ms', 61000)
                f.call('BoardFanControl')
                check(label+'/at30s', int(bool(f.p(872) or f.p(874))), 1)


def parameters(profile):
    f = audit.base()
    f.call('ParameterInit')
    check(f'{profile}/frequency/table-default-min-max',
          [f.var(n, index=177, width=2) for n in ('Parameter_def', 'Parameter_min', 'Parameter_max')],
          [5, 0, 30])
    ptr = 0x20060000
    for value, want in ((-1, 0), (0, 1), (5, 1), (30, 1), (31, 0)):
        frame = bytes([1, 6, 0, 177, (value >> 8) & 255, value & 255])
        f.uc.mem_write(ptr, frame)
        check(f'{profile}/frequency/modbus-write{value}',
              f.call('ModbusWriteValuesValid', ptr, 177, 1), want)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT/'.codex-tmp/four_outdoor_fixes_20261110')
    parser.add_argument('--profile', choices=('PRODUCTION', 'BENCH_ONLY_3S', 'all'), default='all')
    parser.add_argument('--old', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    args.package = args.package.resolve()
    hashes = {}
    profiles = ('PRODUCTION', 'BENCH_ONLY_3S') if args.profile == 'all' else (args.profile,)
    for profile in profiles:
        setup_paths(args.package, profile, args.old)
        for p in (audit.OUT, lifecycle.IN):
            hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
        emergency(profile)
        timed(profile)
        fans(profile)
        fan_scans(profile)
        parameters(profile)
    dest = args.output or args.package/'four_fixes_arm_results.json'
    data = dict(hardware_access=False, artifact_sha256=hashes,
                total=len(RESULTS), passed=sum(r['passed'] for r in RESULTS), results=RESULTS)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"{data['passed']}/{data['total']} passed; {dest}")
    if not args.old:
        assert data['total'] == data['passed'], 'ARM regressions failed; inspect result JSON'


if __name__ == '__main__':
    main()
