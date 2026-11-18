"""Historical V10.38 observations; no serial or physical IO access.

These assertions reproduce audit findings, NOT acceptance tests for the spec.
Run with: py -3 tools/audit_indoor_3133_arm.py
"""
import sys
import hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from test_defrost_lifecycle_arm import indoor, Firmware, OUT, IN, ROOT

BASELINE_SHA256 = 'bddc70eb0c849f38d0926e6e951378c6ca12ca265a5c8c1cee1d6adf7a887c47'
if hashlib.sha256((ROOT / IN).read_bytes()).hexdigest() != BASELINE_SHA256:
    print('SKIP: this historical audit requires the V10.38 baseline AXF. '
          'For current acceptance checks run tools/test_indoor_3133_arm.py.')
    raise SystemExit(0)


def board():
    f = indoor()
    # ParameterInit clears the coil bit-band aliases. No external IO is used.
    f.uc.mem_map(0x22000000, 0x100000)
    f.call('ParameterInit')
    for i in range(500):
        f.p(i, f.var('Parameter_def', index=i, width=2))
    f.p(214, 5)
    f.p(236, 0)
    f.p(700, 4)
    f.p(709, 1)
    f.p(329, 1)
    f.p(330, 0)
    f.p(331, 0)
    f.p(133, 0)
    for i in range(335, 339):
        f.p(i, 0)
    f.var('Systick_1ms', 30000)
    return f


def observe(label, actual, expected):
    assert actual == expected, (label, actual, expected)
    print(label + ': ' + str(actual))


f = board()
f.var('uc1s', 0)
for _ in range(3):
    f.call('SysBoardAction')
observe('no dampers, 3 scans without any one-second tick: supply fan ON',
        f.var('UserPump'), 1)

f = board()
f.p(386, 1)
f.var('Old_SysStep', 1)
f.var('startSeqStep', 5)
f.var('X_15', 1)
f.var('uc1s', 1)
trace = []
for second in range(1, 7):
    # Exact two calls made from UserAction while normal startup is waiting.
    f.call('SysBoardAction')
    f.call('SysDataPross')
    trace.append((second, f.var('supplyOk'), f.p(709)))
    if f.p(709) == 2:
        break
observe('pressure qualification: (injected seconds, supply counter, SysStep)',
        trace, [(1, 2, 1), (2, 4, 1), (3, 6, 1), (4, 8, 1), (5, 10, 1), (6, 10, 2)])

f = board()
f.p(336, 2)  # AO7 belongs to supply damper, fan is DO and OFF.
f.p(130, 50)
f.p(386, 1)
f.var('X_15', 1)
f.var('uc1s', 1)
f.call('IndoorApplyFanValveState', 1, 0, 0, 0)
for _ in range(10):
    f.call('IndoorPressureReady')
observe('damper AO only: fan command, physical DO, qualified counter',
        (f.var('UserPump'), f.var('output', index=3, width=1), f.var('supplyOk')),
        (0, 0, 10))

f = board()
f.p(236, 1)
f.p(128, 2)
f.p(333, 1)
f.p(248, 0)
f.p(709, 3)
f.var('DA', 800, index=0, width=2)
f.var('DA', 800, index=1, width=2)
f.var('uc1s', 0)
f.call('SysBoardAction')
observe('constant-temp heating stop without any elapsed seconds: heat/preheat AO',
        (f.var('DA', index=0, width=2), f.var('DA', index=1, width=2)), (0, 0))

f = board()
f.p(709, 2)
f.p(125, 1)
f.p(248, 1)
f.p(334, 1)
f.call('IndoorDisinfectExhaustAction')  # Observe previous normal mode first.
f.p(236, 3)
f.p(323, 60)
for unit in (1, 2):
    for comp in (0, 1):
        f.field(True, unit, 'CompControl', comp, 1)
        f.field(False, unit, 'CompStatus', comp, 2)
f.var('uc1s', 0)
f.call('IndoorDisinfectExhaustAction')
observe('enter disinfection before humidifier 30s wait: all 4 compressor requests',
        [f.field(True, u, 'CompControl', c) for u in (1, 2) for c in (0, 1)], [0]*4)

f = board()
f.p(709, 0)
f.p(236, 3)
f.p(323, 60)
f.p(163, 0)
f.p(164, 1)
f.p(166, 1)
f.var('uc1s', 1)
for second in range(5, 10):
    f.var('Systick_1ms', second * 1000)
    f.call('UserAction')
observe('actual UserAction during boot 5..9s: saved special-mode run bit cleared', f.p(166), 0)
f.var('Systick_1ms', 20000)
f.call('UserAction')
observe('same board at 20s despite auto restart enabled: SysStatus STOP', f.p(700), 0)

f = board()
f.p(709, 0)
f.p(236, 5)
f.p(326, 1)
f.p(163, 0)
f.p(164, 1)
f.p(166, 1)
f.call('SwitchStatusProcess')
observe('even with saved bit intact, interrupted special mode restored as HEAT', f.p(236), 1)

f = board()
f.p(236, 2)
f.p(709, 2)
f.p(128, 2)
f.p(333, 1)
f.p(346, 200)
f.p(512, -10)
f.call('IndoorStopIndoorLoads')
f.call('IndoorEnforceConfiguredOutputDisable')
observe('ventilation below 0C after final output mask: heat/preheat AO',
        (f.var('DA', index=0, width=2), f.var('DA', index=1, width=2)), (200, 200))
f.p(709, 0)
f.call('IndoorEmergencyStopLoads')
f.call('IndoorEnforceConfiguredOutputDisable')
observe('clear-load helper alone without hard fault flag, then final mask: heat/preheat AO',
        (f.var('DA', index=0, width=2), f.var('DA', index=1, width=2)), (200, 200))
f.p(1406, 1)
f.call('IndoorEmergencyStopLoads')
f.call('IndoorEnforceConfiguredOutputDisable')
observe('actual ModUrgencyStop flag blocks winter minimum: heat/preheat AO',
        (f.var('DA', index=0, width=2), f.var('DA', index=1, width=2)), (0, 0))

f = board()
f.p(709, 2)
f.p(236, 3)
f.p(323, 60)
f.call('IndoorApplyFanValveState', 1, 1, 0, 0)
f.p(700, 0)
f.var('uc1s', 0)
f.call('IndoorDisinfectExhaustAction')
observe('manual stop in special mode without elapsed seconds: fan and SysStep',
        (f.var('UserPump'), f.p(709)), (0, 0))

f = board()
f.p(709, 2)
f.p(236, 1)
f.p(128, 1)
f.p(127, 0)
f.p(129, 1)
f.p(332, 1)
f.field(False, 1, 'CanDefrost', value=8)
f.call('HeatControl_UP')
observe('heat-pump defrost with aux AO selected, reheat disabled: auxiliary AO',
        f.var('DA', index=0, width=2), 0)
f.p(127, 1)
f.call('HeatControl_UP')
observe('same configuration with reheat enabled: auxiliary AO',
        f.var('DA', index=0, width=2), 1000)

f = board()
f.p(1153, 100)
f.var('uc1s', 0)
target = f.call('EEVCloseStepTarget', 0, 100, 500)
observe('330 close init: (position bookkeeping, close target), no extra10',
        (f.p(1153), target), (100, 100))
f.var('uc1s', 1)
observe('330 close first 1s target', f.call('EEVCloseStepTarget', 0, 100, 500), 80)

f = Firmware(OUT)
f.p(10, 500)
f.p(12, 500)
f.p(809, 100)
f.var('uc1s', 0)
target = f.call('EEVCloseStepTarget', 0, 100, 2)
observe('316 emergency close init: (position bookkeeping, close target), includes extra10',
        (f.p(809), target), (110, 110))
f.var('uc1s', 1)
observe('316 emergency close first 1s target', f.call('EEVCloseStepTarget', 0, 100, 2), 90)
