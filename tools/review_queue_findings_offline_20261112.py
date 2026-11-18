"""Review paused-bench findings in pinned ARM images; never accesses hardware.

Fixtures are synthetic RAM in Unicorn. These checks reproduce decision paths,
not UART transport, full board scheduling, or physical terminals.
"""
import hashlib
import json
from test_defrost_lifecycle_arm import Firmware, ROOT

PACKAGE = ROOT / '.codex-tmp/restart_guard_v1060_v1243_20261112'
DEST = ROOT / '测试证据/剩余全队列_20261112/代码复核_ARM离线_20261112.json'


def image(profile, indoor):
    version = 'PSC330_V10.60' if indoor else 'PSC316_V12.43'
    path = PACKAGE / profile / f'{version}_{profile}.axf'
    return Firmware(path), path


def indoor_gate(profile, temperature, prior_flag=0, mode=1):
    f, path = image(profile, True)
    # Match recorded thresholds. Faulted unit1 is already excluded; unit2 is
    # healthy and running, with minimum run and action interval satisfied.
    for address, value in {1: mode, 236: mode, 99: 1, 214: 3, 709: 2,
                           278: 0, 279: 600, 280: -120, 281: 350,
                           737: prior_flag, 707: 0}.items():
        f.p(address, value)
    for address in range(250, 254):
        f.p(address, 1)
    f.field(False, 1, 'AII', 4, temperature)
    for unit in (1, 2):
        for comp in (0, 1):
            f.field(False, unit, 'CompStatus', comp, 1 if unit == 1 else 3)
            f.field(True, unit, 'CompControl', comp, 0 if unit == 1 else 1)
            f.var('CompMinRunCount', 1000, 2 * unit + comp, 4)
    f.var('Systick_1ms', 100000)
    f.call('CompMainAction')
    first = [f.field(True, 2, 'CompControl', c) for c in (0, 1)]
    for c in (0, 1):
        if not first[c]:
            f.field(False, 2, 'CompStatus', c, 0)
    # Feed the changed command/output through the real interval tracker.
    f.call('CompActionIntervalUpdate')
    f.var('Systick_1ms', 140000)
    f.call('CompMainAction')
    second = [f.field(True, 2, 'CompControl', c) for c in (0, 1)]
    result = dict(profile=profile, mode=mode, temperature10=temperature,
                  prior_global_flag=prior_flag, global_flag=f.p(737),
                  healthy_unit2_first=first, healthy_unit2_second=second)
    if temperature == 9999 or (mode == 0 and temperature == -20):
        assert result['global_flag'] == 1 and sum(first) == 1 and second == [0, 0], result
    else:
        assert result['global_flag'] == 0 and first == second == [1, 1], result
    return result, path


def outdoor_43(profile):
    f, path = image(profile, False)
    for address, value in {1: 0, 165: 1, 166: 3, 1298: 3, 1422: 430}.items():
        f.p(address, value)
    f.var('output', 1, 0, 1)
    f.call('AmbientProtectAction')  # Initialize changed mode/type/profile.
    f.var('AmbientLockout', 0)  # Synthetic already-permitted running state.
    f.var('uc1s', 1)
    for _ in range(59):
        f.call('AmbientProtectAction')
    at59 = f.var('AmbientLockout')
    f.call('AmbientProtectAction')
    at60 = f.var('AmbientLockout')
    f.var('AmbientLockout', 0)
    f.var('output', 0, 0, 1)
    f.var('uc1s', 0)
    f.call('AmbientProtectAction')
    stopped = f.var('AmbientLockout')
    assert (at59, at60, stopped) == (0, 1, 1)
    return dict(profile=profile, continuously_running_at59=at59,
                continuously_running_at60=at60,
                stopped_at43_next_call=stopped,
                scope='Actual AmbientProtectAction; synthetic one-second task pulses'), path


def phase6(profile):
    f, path = image(profile, False)
    f.var('BoardAddressSet', 1)
    f.var('PSC316DefrostState', 0)
    # Comp1Err/Comp2Err are Parameter[800]/[801] in the bound User.h.
    f.p(800, 1)
    f.p(801, 1)
    f.call('DefUnusualOut')
    phases = [f.field(False, 1, 'CanDefrost', c, width=4) for c in (0, 1)]
    signals = [f.field(True, 1, 'DefrostSignal', c, width=4) for c in (0, 1)]
    assert phases == [6, 6] and signals == [0, 0] and f.var('PSC316DefrostState') == 0
    return dict(profile=profile, completed_state=0, fault_phases=phases,
                cleared_signals=signals), path


def low_pressure_mask(profile):
    f, path = image(profile, False)
    f.var('BoardAddressSet', 1)
    for address, value in {1: 1, 27: 1, 60: 5, 107: 1, 1444: 500, 54: 150}.items():
        f.p(address, value)
    f.var('CompRunTime', 200, 0, 4)
    f.var('EnableCheckLow', 1, 0, 4)
    f.var('X01_En', 1)
    f.var('uc100ms', 1)
    f.field(True, 1, 'DefrostSignal', 0, 1, width=4)
    for _ in range(100):
        f.call('CompErrAction')
    masked = f.p(600)
    f.field(True, 1, 'DefrostSignal', 0, 0, width=4)
    for _ in range(49):
        f.call('CompErrAction')
    at49 = f.p(600)
    f.call('CompErrAction')
    at50 = f.p(600)
    assert (masked, at49, at50) == (0, 0, 1)
    return dict(profile=profile, active_defrost_100_ticks_alarm=masked,
                postdefrost_49_ticks_alarm=at49, postdefrost_50_ticks_alarm=at50,
                scope='Actual CompErrAction with synthetic 100ms pulses; no physical DI/UART'), path


def main():
    result = dict(scope='ARM offline only; paused hardware untouched',
                  indoor_gate=[], outdoor_43=[], phase6=[], low_pressure_mask=[],
                  artifacts={}, source_checks={})
    for profile in ('BENCH_ONLY_3S', 'PRODUCTION'):
        manifest = json.loads((PACKAGE / profile / 'manifest.json').read_text(encoding='utf-8-sig'))
        mismatch = [name for name, digest in manifest['source_inventory'].items()
                    if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
        assert not mismatch, mismatch
        result['source_checks'][profile] = dict(count=len(manifest['source_inventory']), mismatches=mismatch)
        for temperature, prior in ((155, 0), (9999, 0), (155, 1)):
            row, path = indoor_gate(profile, temperature, prior)
            result['indoor_gate'].append(row)
            result['artifacts'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        row, _ = indoor_gate(profile, -20, mode=0)
        result['indoor_gate'].append(row)
        for key, fn in (('outdoor_43', outdoor_43), ('phase6', phase6),
                        ('low_pressure_mask', low_pressure_mask)):
            row, path = fn(profile)
            result[key].append(row)
            result['artifacts'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    DEST.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
