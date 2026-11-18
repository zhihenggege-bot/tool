"""Test production/BENCH boundaries in built ARM images; no hardware access."""
import importlib.util
import json
import sys
from pathlib import Path

from test_defrost_lifecycle_arm import Firmware, ROOT

RELEASE = ROOT/'.codex-tmp/sequence_timing_v1047_v1238_20261104'
checks = []


def check(condition, label):
    assert condition, label
    checks.append(label)
    print('PASS', label)


def image(model, bench):
    profile = 'BENCH_ONLY_3S' if bench else 'PRODUCTION'
    version = '10.47' if model == 330 else '12.38'
    f = Firmware(str((RELEASE/profile/f'PSC{model}_V{version}_{profile}.axf').relative_to(ROOT)))
    f.uc.mem_map(0x22000000, 0x100000)
    f.call('ParameterInit')
    return f


def comp_fixture(bench):
    f = image(330, bench)
    f.p(214, 2)
    f.p(250, 1)
    f.var('PSC316SetValid', 1, 0, 1)
    f.var('Systick_1ms', 36000)
    return f


def ambient_fixture(bench, mode=0, duration=3, unit_type=0):
    f = image(316, bench)
    for addr, value in {1: mode, 165: unit_type, 170: 150, 171: 180,
                        1422: 200 if mode == 0 else 50, 1298: duration}.items():
        f.p(addr, value)
    f.call('AmbientProtectAction')  # starts a new confirmation window
    return f


def tick_ambient(f, seconds):
    f.var('uc1s', 1)
    for _ in range(seconds):
        f.call('AmbientProtectAction')
    f.var('uc1s', 0)


def test_firmware():
    for bench in (False, True):
        label = 'BENCH' if bench else 'production'
        stop, run = (3, 3) if bench else (120, 180)
        for model in (330, 316):
            f = image(model, bench)
            check(f.p(1299) == (0x3B03 if bench else 0), f'{model} {label}: read-only profile initialized')
            check(f.var('Parameter_min', index=42, width=2) == stop and
                  f.var('Parameter_min', index=43, width=2) == run,
                  f'{model} {label}: both parameter timing ranges match profile')
            check(f.p(1298) == (3 if bench else 300), f'{model} {label}: recovery RAM default')
            check(f.var('Parameter_def', index=42, width=2) == 120 and
                  f.var('Parameter_def', index=43, width=2) == 180,
                  f'{model} {label}: production EEPROM defaults stay 120/180')
        f = comp_fixture(bench)
        f.p(42, 3)  # production must retain its hard floor even if RAM is poisoned
        f.var('CompMinStopCount', stop-1, 2, 4)
        check(f.call('CompCanLoad', 1, 0) == 0, f'330 {label}: no start before minimum')
        f.var('CompMinStopCount', stop, 2, 4)
        check(f.call('CompCanLoad', 1, 0) == 1, f'330 {label}: start at minimum')
        f.p(43, 3)
        f.field(False, 1, 'CompStatus', 0, 3)
        f.field(True, 1, 'CompControl', 0, 1)
        f.var('CompMinRunCount', run-1, 2, 4)
        check(f.call('CompCanUnload', 1, 0) == 0, f'330 {label}: no unloading before minimum')
        f.var('CompMinRunCount', run, 2, 4)
        check(f.call('CompCanUnload', 1, 0) == 1, f'330 {label}: unloading at minimum')
        check(f.call('ParamCanWriteFromHMI', 1299, 0x3B03) == 0,
              f'330 {label}: cannot spoof profile through HMI')
        check(f.call('ParamCanWriteFromHMI', 1298, 3) == int(bench),
              f'330 {label}: short recovery permission')
        check(f.call('ParamCanWriteFromHMI', 1298, 2) == 0 and
              f.call('ParamCanWriteFromHMI', 1298, 301) == 0,
              f'330 {label}: recovery range checked')
        f = image(316, bench)
        check(f.call('ModbusWriteOverlapsReadOnly', 1298, 2) == 1,
              f'316 {label}: FC16 including profile marker rejected')
        f.var('BoardAddressSet', 1)
        f.p(1400, 1)
        f.p(45, 0)
        f.p(42, 3)
        f.var('output', 1, 2, 1)
        f.var('CompStopTime', stop-1, 0, 4)
        f.call('ModuleCompAction')
        f.var('Systick_1ms', 1000)
        f.call('ModuleCompAction')
        check(f.var('Comp', index=0, width=1) == 0, f'316 {label}: own start floor is enforced')
        f.var('CompStopTime', stop, 0, 4)
        f.call('ModuleCompAction')
        check(f.var('Comp', index=0, width=1) == 1, f'316 {label}: starts at own floor')
        for mode in (0, 1):
            f = ambient_fixture(bench, mode=mode)
            need = 3 if bench else 300
            tick_ambient(f, need-1)
            check(f.var('AmbientLockout', width=1) == 1, f'316 {label}: mode {mode} locks until {need}s')
            tick_ambient(f, 1)
            check(f.var('AmbientLockout', width=1) == 0, f'316 {label}: mode {mode} recovers at {need}s')
            check(f.p(1298) == need, f'316 {label}: mode {mode} cannot retain poisoned recovery')
        f = ambient_fixture(bench)
        f.var('SensorStatus', 1, 6, 1)
        tick_ambient(f, 301)
        check(f.var('AmbientLockout', width=1) == 1, f'316 {label}: faulty ambient sensor still locks')
    f = ambient_fixture(True, duration=10)
    tick_ambient(f, 9)
    check(f.var('AmbientLockout', width=1) == 1, 'BENCH adjustable recovery waits 10 seconds')
    tick_ambient(f, 1)
    check(f.var('AmbientLockout', width=1) == 0, 'BENCH adjustable recovery ends at 10 seconds')
    f.p(1298, 20)
    f.call('AmbientProtectAction')
    check(f.var('AmbientLockout', width=1) == 1, 'changing recovery resets confirmation window')
    tick_ambient(f, 19)
    check(f.var('AmbientLockout', width=1) == 1, 'new recovery duration is not satisfied by old counters')
    tick_ambient(f, 1)
    check(f.var('AmbientLockout', width=1) == 0, 'changed recovery finishes new window')
    for unit_type in (1, 2):
        f = ambient_fixture(True, unit_type=unit_type)
        tick_ambient(f, 3)
        check(f.var('AmbientLockout', width=1) == 0, f'BENCH ambient type {unit_type} uses recovery setting')


def test_monitor():
    app_path = ROOT/'psc330_monitor_tool/psc330_monitor/app.py'
    sys.path.insert(0, str(app_path.parent))
    spec = importlib.util.spec_from_file_location('bench_monitor_app', app_path)
    app = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = app
    spec.loader.exec_module(app)
    for profile in (None, 0, 0x3B03):
        for addr, minimum in ((42, 120), (43, 180), (1298, 300)):
            check(app.timing_minimum(addr, minimum, profile) == (3 if profile == 0x3B03 else minimum),
                  f'monitor {profile}: address {addr} minimum')
    class FakeApp:
        def __init__(self, marker, stopped=0):
            self.marker, self.stopped = marker, stopped
            self.writes = []
            self.values = {}
        def read_now(self, addr, count):
            if addr == 1299: return [self.marker]
            if addr == 709: return [self.stopped]
            return [dict(self.writes)[addr] & 65535]
        def write_single(self, addr, value):
            self.writes.append((addr, value))
    for marker, stopped in ((0, 0), (0x3B03, 2)):
        f = FakeApp(marker, stopped)
        try:
            app.Psc330MonitorApp._write_mode_config_block(f, {42: 3, 43: 3})
            raise AssertionError('short timing was accepted')
        except ValueError:
            pass
        check(not f.writes, f'monitor fresh marker {marker}, step {stopped}: reject before writes')
    f = FakeApp(0x3B03)
    app.Psc330MonitorApp._write_mode_config_block(f, {42: 3, 43: 3, 1298: 3})
    check(f.writes == [(42, 3), (43, 3), (1298, 3)], 'monitor BENCH: short timing writes and readbacks')


if __name__ == '__main__':
    test_firmware()
    test_monitor()
    (RELEASE/'timing_test_result.json').write_text(
        json.dumps({'checks_passed': len(checks), 'checks': checks,
                    'hardware_access': False}, indent=2) + '\n', encoding='utf-8')
    print(len(checks), 'timing profile checks passed')
