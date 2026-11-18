"""Execute both V10.50 ARM images; stub adjacent tasks only for scan-order tests.

No board/RAM writes. Full startup/shutdown regression is run separately.
"""
import hashlib
import json
from test_defrost_lifecycle_arm import Firmware, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR

PACKAGE = ROOT / '.codex-tmp/runtime_count_v1050_v1239_20261105'
checks = []


def check(ok, label):
    checks.append({'label': label, 'passed': bool(ok)})
    assert ok, label


def board(profile, isolate=False):
    f = Firmware(str(PACKAGE / profile / f'PSC330_V10.50_{profile}.axf'))
    f.uc.mem_map(0x22000000, 0x100000)
    f.call('ParameterInit')
    for a in range(500):
        f.p(a, f.var('Parameter_def', index=a, width=2))
    f.p(214, 3)
    for a in range(250, 258):
        f.p(a, 1)
    if isolate:
        # Execute actual UserAction, refresh and auto-switch. Other tasks are
        # skipped to hold each early-return path/feedback fixture stationary.
        names = ('SwitchStatusProcess', 'IndoorNormalizeWorkMode',
                 'IndoorModeTransitionAction', 'IndoorDisinfectExhaustAction',
                 'IndoorPressureReady', 'EEV_ActionAll', 'EEV_Priority',
                 'FanAction', 'SysBoardAction', 'SysDataPross',
                 'IndoorClearOutdoorRunCommands', 'IndoorStopHeatPreheatLoads',
                 'IndoorStopHumidifier', 'IndoorStopIndoorLoads',
                 'IndoorFanValveOutputs', 'PreHeatControl', 'SysNergryAction_PID',
                 'SysNergryAction', 'CompAction', 'VVFCtrl', 'HeatControl_UP',
                 'HumidtCtrl', 'ColdWaterValveDA8Control', 'ReHeatY11Control',
                 'IndoorApplyHeatAnalogOutputs')
        addresses = {f.symbols[n][0] & ~1 for n in names if n in f.symbols}
        def stub(uc, pc, size, _):
            if pc in addresses:
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        f.uc.hook_add(UC_HOOK_CODE, stub)
        f.var('uc1s', 1)
        f.p(320, 0)
        for _ in range(5):
            f.call('UserAction')
    return f


def statuses(f, values):
    for unit in range(1, 5):
        for comp in range(2):
            idx = (unit-1)*2+comp
            f.field(False, unit, 'CompStatus', comp,
                    values[idx] if idx < len(values) else 0)


def run():
    for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
        f = board(profile)
        # Normal, stopped, preparing, cooling/heating, defrost states.
        for values, want in [([0, 0, 0, 0], 0), ([1, 1, 1, 1], 0),
                             ([2, 0, 0, 0], 1), ([2, 3, 4, 0], 3),
                             ([4, 4, 4, 4], 4)]:
            statuses(f, values)
            f.p(119, 99)
            f.call('IndoorRefreshRunningCompNum')
            check(f.p(119) == want, f'{profile}: actual states {values} -> {want}')
        # Keep the preexisting config and communication eligibility semantics.
        f.p(214, 5)
        statuses(f, [2]*8)
        f.call('IndoorRefreshRunningCompNum')
        check(f.p(119) == 8, f'{profile}: all four configured units counted')
        f.p(250, 0)
        f.var('UnitCommErr', 1, index=2, width=2)
        f.call('IndoorRefreshRunningCompNum')
        check(f.p(119) == 5, f'{profile}: existing disabled/communication filters unchanged')
        f.p(214, 1)
        f.call('IndoorRefreshRunningCompNum')
        check(f.p(119) == 0, f'{profile}: no outdoor units -> zero')

        for mode in range(6):
            for step in range(6):
                f = board(profile, True)
                f.p(236, mode); f.p(1, mode); f.p(709, step)
                for states, want in [([2, 0, 0, 0], 1), ([0]*4, 0)]:
                    statuses(f, states); f.p(119, 7)
                    f.call('UserAction')
                    check(f.p(119) == want,
                          f'{profile}: UserAction mode{mode}/step{step} refresh -> {want}')

        # Full UserAction (no task stubs): sensor partial-stop bypass must
        # keep actual feedback until the outdoor compressor actually stops.
        f = board(profile)
        f.p(38,0); f.p(320,0); f.p(398,0); f.p(164,0)
        f.var('uc1s',1); f.var('Systick_1ms',30000)
        for _ in range(5):f.call('UserAction')
        f.var('IndoorSensorPartialStopFlag',1)
        f.p(236,0); f.p(1,0); f.p(709,2)
        for states,want in [([2,0,0,0],1),([0,0,0,0],0)]:
            statuses(f,states); f.p(119,7); f.call('UserAction')
            check(f.p(119)==want,
                  f'{profile}: full sensor-stop UserAction actual count -> {want}')

        # A stale 0 must not permit switching with two actual compressors;
        # stale 3 must not block switching with <=1. Run actual auto-switch.
        for humidity in (0, 1):
            f = board(profile, True)
            for a, v in {236:0, 1:0, 709:2, 320:1, 321:50, 322:60,
                         125:humidity, 248:humidity, 127:1, 332:1,
                         890:600}.items():
                f.p(a, v)
            statuses(f, [2, 3, 0, 0]); f.p(119, 0)
            for _ in range(61):
                f.call('UserAction')
            check(f.p(236) == 0 and f.p(884) == 0 and f.p(119) == 2,
                  f'{profile}: humidity{humidity} actual2 blocks stale0 switch')
            statuses(f, [2, 0, 0, 0]); f.p(119, 3)
            for _ in range(59):
                f.call('UserAction')
            check(f.p(236) == 0 and f.p(884) == 59 and f.p(119) == 1,
                  f'{profile}: humidity{humidity} actual1 counts QHS without stale3 block')
            f.call('UserAction')
            check(f.p(236) == 1,
                  f'{profile}: humidity{humidity} switches after full QHS60')
    print(len(checks), 'runtime count ARM checks passed')


if __name__ == '__main__':
    try:
        run()
    finally:
        (PACKAGE / 'runtime_count_ARM.json').write_text(json.dumps({
            'hardware_access': False, 'scan_order_tests_stub_adjacent_tasks': True,
            'checks': checks, 'passed': bool(checks) and all(c['passed'] for c in checks),
            'artifacts_sha256': {str(p.relative_to(PACKAGE)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in PACKAGE.glob('*/*.axf')}
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
