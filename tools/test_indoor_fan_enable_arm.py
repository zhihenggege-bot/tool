"""Exercise AO fan run relays through final ARM output and shutdown paths.

No hardware, serial or flashing. Run after building V10.49 both profiles.
"""
import hashlib
import json
from test_defrost_lifecycle_arm import Firmware, ROOT
from test_indoor_3133_arm import at, out, ao

D = ROOT / '.codex-tmp/persistence_interlock_v1049_v1239_20261105'
checks = []


def check(ok, label):
    checks.append({'label': label, 'passed': bool(ok)})
    assert ok, label


def board(bench, mode=2, supply=2, returning=2):
    profile = 'BENCH_ONLY_3S' if bench else 'PRODUCTION'
    f = Firmware(str((D / profile / f'PSC330_V10.49_{profile}.axf').relative_to(ROOT)))
    f.uc.mem_map(0x22000000, 0x100000)
    f.call('ParameterInit')
    for a in range(500):
        f.p(a, f.var('Parameter_def', index=a, width=2))
    for a, v in {38: 0, 214: 3, 236: mode, 1: mode, 700: 4, 709: 1,
                 329: supply, 330: returning, 331: 1, 328: 30, 132: 30,
                 135: 30, 381: 0, 386: 0, 153: 0, 134: 50, 131: 50,
                 341: 50, 342: 100}.items():
        f.p(a, v)
    for a in range(335, 339):
        f.p(a, 0)
    for a in range(250, 258):
        f.p(a, 1)
    f.var('OilCount', 10000)
    f.var('Systick_1ms', 30000)
    f.p(926, 500)  # Auto fan demand is otherwise supplied by FanAction.
    return f


def final(f):
    # Same output ordering as User(): constraint, legacy writer, constraint.
    for fn in ['IndoorEnforceConfiguredOutputDisable', 'IoOutAction',
               'IndoorEnforceConfiguredOutputDisable']:
        f.call(fn)


def state(f, supply=1, returning=1):
    f.call('IndoorApplyFanValveState', 1, supply, returning, 1)
    final(f)


def cycle(f, sec):
    at(f, sec, 'SysBoardAction', 'SysDataPross', 'IndoorFanValveOutputs')
    final(f)


def run():
    for bench in [False, True]:
        tag = 'BENCH' if bench else 'production'
        for supply in [2, 3]:
            for volt in [0, 50, 100]:
                f = board(bench, supply=supply)
                f.p(134, volt)
                f.p(131, volt)
                f.p(926, volt * 10)
                state(f)
                check(out(f, 3) == out(f, 6) == 1,
                      f'{tag} supply mode{supply}, {volt/10}V: both run relays survive final writers')
                if supply == 2:
                    check(ao(f, 7) == volt*10, f'{tag} supply manual {volt/10}V setpoint preserved')
                check(ao(f, 4) == volt*10, f'{tag} return manual {volt/10}V setpoint preserved')
                check(f.call('IndoorSupplyFanOn') == f.call('IndoorReturnFanOn') == 1,
                      f'{tag} mode{supply} {volt/10}V: run relays remain part of shutdown snapshot')
                state(f, 0, 0)
                check(not any(out(f, c) for c in [3, 6]) and ao(f, 7) == ao(f, 4) == 0,
                      f'{tag} mode{supply} {volt/10}V: stop clears both relays and speed outputs')
        for supply in [1, 2, 3]:
            f = board(bench, supply=supply)
            # Shared AO7 supply valve suppresses AO fan and its run relay.
            if supply != 1:
                f.p(336, 2)
                state(f)
                check(out(f, 3) == 0 and ao(f, 7) == 0,
                      f'{tag} mode{supply}: DA7 ownership conflict cannot energize run relay')
            f = board(bench, supply=supply)
            f.p(337, 2)
            state(f)
            check(out(f, 6) == 0 and ao(f, 4) == 0,
                  f'{tag} mode{supply}: DA4 ownership conflict cannot energize return relay')
        f = board(bench, supply=0, returning=0)
        state(f)
        check(not out(f, 3) and not out(f, 6) and ao(f, 7) == ao(f, 4) == 0,
              f'{tag}: disabled fan types stay off')
        for cause, register in [('SysErrStatus', 710), ('ModUrgencyStop', 1406),
                                ('UserSidePumpOverLoadErr', 601)]:
            f = board(bench)
            state(f)
            f.p(register, 1)
            f.call('IndoorEmergencyStopLoads')
            final(f)
            check(not any(out(f, c) for c in [3, 6, 10]) and ao(f, 7) == ao(f, 4) == 0,
                  f'{tag}: emergency cleanup after {cause} cannot be undone by legacy writer')
        gap = 3 if bench else 30
        wait = 3 if bench else 10
        close = 3 if bench else 30
        for supply in [2, 3]:
            for volt in [0, 50]:
                f = board(bench, supply=supply)
                f.p(134, volt)
                f.p(131, volt)
                for sec, expected in [(0, (0, 0, 0)), (wait-.001, (0, 0, 0)),
                                      (wait, (0, 0, 1)), (wait+gap, (1, 0, 1)),
                                      (wait+gap*2, (1, 1, 1))]:
                    cycle(f, sec)
                    check(tuple(out(f, c) for c in [3, 6, 10]) == expected,
                          f'{tag} AO mode{supply} {volt/10}V: timed startup at{sec}s')
                stop = wait+gap*2+2
                f.p(700, 0)
                cycle(f, stop)  # First scan records the normal stop edge (step 2 -> 3).
                for sec, expected in [(stop, (0, 1, 1)),
                                      (stop+gap-.001, (0, 1, 1)),
                                      (stop+gap, (0, 0, 1)),
                                      (stop+gap*2, (0, 0, 0))]:
                    cycle(f, sec)
                    check(tuple(out(f, c) for c in [3, 6, 10]) == expected,
                          f'{tag} AO mode{supply} {volt/10}V: timed shutdown at{sec}s')
                cycle(f, stop+gap*2+close)
                check(f.p(709) == 0 and ao(f, 7) == ao(f, 4) == 0,
                      f'{tag} AO mode{supply} {volt/10}V: shutdown completes with outputs off')
        # A lost airflow input in steady run must still execute the 60+10s timer.
        f = board(bench)
        f.p(386, 2)
        f.p(709, 2)
        state(f)
        for sec in [0, 59.999, 60, 69.999]:
            at(f, sec, 'SysDataPross')
            check(f.p(912) == 0, f'{tag}: running AO airflow fault not early at{sec}s')
        at(f, 70, 'SysDataPross')
        check(f.p(912) == 1, f'{tag}: running AO airflow fault at60+10s')


if __name__ == '__main__':
    try:
        run()
    finally:
        D.mkdir(parents=True, exist_ok=True)
        (D / 'fan_enable_test_result.json').write_text(json.dumps({
            'scope': 'Actual ARM offline, no physical terminal or hardware test',
            'checks': checks, 'passed': bool(checks) and all(c['passed'] for c in checks),
            'artifacts_sha256': {str(p.relative_to(D)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in D.glob('*/*.axf')}
        }, ensure_ascii=False, indent=2), 'utf-8')
    print(len(checks), 'fan enable checks passed')
