"""Offline specification observations against pinned V12.39/V10.55 ARM builds.

No hardware/serial/debug probe access. Does not modify firmware or accept tests.
Exit 0 means evidence was written; inspect each PASS/FAIL/OBSERVATION result.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

from test_defrost_lifecycle_arm import Firmware, ROOT

PACKAGE = ROOT / '.codex-tmp/special_display_v1055_v1239_20261109'
OUT = PACKAGE / 'PRODUCTION/PSC316_V12.39_PRODUCTION.axf'
IN = PACKAGE / 'PRODUCTION/PSC330_V10.55_PRODUCTION.axf'
DEST = ROOT / '测试证据/外机规格离线核对_20261109'
results = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(key, clause, observed, expected=None):
    status = 'OBSERVATION' if expected is None else ('PASS' if observed == expected else 'FAIL')
    results.append(dict(id=key, clause=clause, status=status, observed=observed, expected=expected))


def base(mode=0, unit_type=0, fan_type=1):
    f = Firmware(OUT)
    f.var('BoardAddressSet', 1)
    for a, v in {1: mode, 41: 30, 56: 3800, 60: 5, 107: 1,
                 165: unit_type, 166: fan_type, 170: 150, 171: 180,
                 172: 300, 173: 150, 174: 70, 175: 50, 176: 50,
                 177: 5, 178: 10, 179: 30, 180: 30, 181: 60,
                 182: 100, 183: 30, 184: 4, 185: 10, 186: -20,
                 187: 100, 188: 30, 189: 35, 190: 400, 191: 4,
                 192: 3, 197: 1, 1422: 50}.items():
        f.p(a, v)
    return f


def running(f, first=1, second=1):
    for i, value in enumerate((first, second)):
        f.var('output', value, i, 1)
        f.var('Comp', value, i, 1)


def defrost():
    f = base(1)
    f.p(1409, 1)
    f.p(1410, 1)
    running(f)
    f.call('DefrostProcess')
    assert f.p(1420) == f.p(1421) == 8, 'Fixture must enter active defrost'
    return f


def second(f, t, handler):
    f.var('uc1s', 1)
    f.var('Systick_1ms', t*1000)
    return f.call(handler)


def main():
    manifest = json.loads((PACKAGE / 'PRODUCTION/manifest.json').read_text())
    changes = [p for p, h in manifest['source_inventory'].items()
               if not (ROOT/p).exists() or sha(ROOT/p) != h]
    assert not changes, f'Pinned source inventory changed: {changes}'
    for p in (IN, OUT):
        assert sha(p) == manifest['artifacts'][p.name], 'Pinned AXF hash mismatch'

    f = base()
    f.call('ParameterInit')
    # Runtime ParameterInit overrides some literal initializer values.
    expected = {
        170: (150, 150, 250), 171: (180, 50, 200),
        172: (300, 200, 350), 173: (150, 100, 200),
        174: (70, 50, 100), 175: (50, 30, 80),
        176: (50, 30, 50), 177: (5, 0, 30), 178: (10, 1, 20),
        179: (30, 10, 300), 180: (30, 10, 300), 181: (60, 0, 300),
        182: (100, 50, 150), 183: (30, 20, 50), 184: (4, 2, 8),
        185: (10, 5, 30), 186: (-20, -40, -10), 187: (100, 50, 150),
        188: (30, 15, 60), 189: (35, 15, 70), 190: (400, 300, 600),
        191: (4, 2, 8), 192: (3, 2, 8), 193: (30, 20, 120),
    }
    for a, want in expected.items():
        got = [f.var(n, index=a, width=2) for n in ('Parameter_def', 'Parameter_min', 'Parameter_max')]
        got = [x-65536 if x >= 32768 else x for x in got]
        record(f'PARAM-{a}', '4.1/4.3/4.4/4.5', got, list(want))

    # Cooling stop diagram has literal 13 C; code substitutes LWS-2 C.
    f = base()
    f.p(170, 220)
    f.p(1422, 250)
    f.call('AmbientProtectAction')
    for t in range(1, 301): second(f, t, 'AmbientProtectAction')
    assert f.var('AmbientLockout') == 0
    running(f)
    f.p(1422, 190)
    for t in range(301, 601): second(f, t, 'AmbientProtectAction')
    record('AMB-LWS22-STOP19', '4.1/制冷图13℃停止线', f.var('AmbientLockout'), 0)

    for mode, temp, label in ((0, 200, 'COOL'), (1, 100, 'HEAT')):
        f = base(mode)
        f.p(1422, temp)
        f.call('AmbientProtectAction')
        for t in range(1, 300): second(f, t, 'AmbientProtectAction')
        before = f.var('AmbientLockout')
        second(f, 300, 'AmbientProtectAction')
        record(f'AMB-{label}-300', '4.1', [before, f.var('AmbientLockout')], [1, 0])

    f = base()
    f.p(1422, 200)
    f.call('AmbientProtectAction')
    for t in range(1, 301): second(f, t, 'AmbientProtectAction')
    running(f)
    f.p(1422, 430)
    for t in range(301, 360): second(f, t, 'AmbientProtectAction')
    before = f.var('AmbientLockout')
    second(f, 360, 'AmbientProtectAction')
    record('AMB-43-OBS', '4.1/图的60秒方向待解释', [before, f.var('AmbientLockout')])

    # TypeIII uses pressure-derived condensing temperature. Hook only the input
    # conversion, leaving the actual fan state machine and gates executable.
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_LR

    def fan(typ=4, temp=400, speed=200, fixed=0):
        g = base(0, 2, typ)
        for name, value in [('OutdoorVfdOn', 1), ('OutdoorFixedOn', fixed),
                            ('OutdoorVfdSpeed', speed), ('OutdoorFanChangeSeconds', 100)]:
            g.var(name, value)
        for i in range(2):
            g.var('OutdoorFanStopSeconds', 100, i, 4)
            g.var('OutdoorFanRunSeconds', 100, i, 4)
        def input_max(uc, address, size, data):
            uc.reg_write(UC_ARM_REG_R0, temp)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        address = g.symbols['OutdoorCondTempMax'][0] & ~1
        g.uc.hook_add(UC_HOOK_CODE, input_max, begin=address, end=address)
        return g

    f = fan(temp=360)
    for t in range(1, 32): second(f, t, 'OutdoorFanTypeIII')
    record('FAN-DUAL-36-EQUALITY', '4.3.1/双风机图!所有<36', f.var('OutdoorVfdSpeed'), 220)
    for temp, want, label in ((339, 190, 'UNLOAD'), (350, 200, 'HOLD'), (361, 210, 'LOAD')):
        f = fan(2, temp=temp)
        for t in range(1, 31): second(f, t, 'OutdoorFanTypeIII')
        record(f'FAN-SINGLE-{label}', '4.3.1/单变频', f.var('OutdoorVfdSpeed'), want)

    for typ in (0, 1, 2, 3, 4):
        f = base(0, (0 if typ < 2 else 1 if typ == 3 else 2), typ)
        # Establish actual on -> off edges, so millisecond gates (type 1)
        # and seconds gates both represent a just-stopped fan, not power-up.
        f.p(872, 1)
        f.p(874, 1)
        f.var('Systick_1ms', 1000)
        f.call('OutdoorFanUpdateTimers')
        f.p(872, 0)
        f.p(874, 0)
        f.var('Systick_1ms', 31000)
        f.call('OutdoorFanUpdateTimers')
        f.var('Systick_1ms', 31001)
        f.var('uc1s', 0)
        f.call('OutdoorFanPrestart')
        record(f'FAN-PRESTART-MINSTOP-{typ}', '4.3/风机最小停机时间', f.p(872), 0)

    # Timed fallback threshold can be 15 C but has a second hardcoded <10 check.
    f = base(1)
    f.p(182, 150)
    f.p(1422, 120)
    f.p(613, 1)  # Fin1TempErr: a nonambient fault selects timed mode.
    running(f, 0, 1)
    f.var('CompRunTime', 1801, 1, 4)
    f.var('DefGapCount', 1801, 1, 4)
    for t in range(1, 62): second(f, t, 'DefEnable')
    record('DEF-TIMED-12-LIMIT15', '4.4/环境定时设定5～15℃', f.var('DefComp0', index=1, width=4), 1)

    f = defrost()
    f.var('X_00', 1)
    f.call('CompErrAction')
    f.call('DefrostProcess')
    record('DEF-HP-SYSTEM1-EXIT', '4.4/4.6.4',
           [f.var('Comp', index=i, width=1) for i in range(2)] + [f.p(606)], [0, 1, 0])
    f.var('X_02', 1)
    f.call('DefrostProcess')
    before = [f.p(1420), f.p(1421)]
    for t in range(1, 60): second(f, t, 'DefrostProcess')
    at59 = f.p(1420)
    second(f, 60, 'DefrostProcess')
    record('DEF-PRODUCTION-RECOVERY60', '4.4', before+[at59, f.p(1420)], [7, 7, 7, 0])

    for label, address in (('UNIT', 167), ('COMP2', 153)):
        f = defrost()
        f.p(address, 1)
        for t in range(1, 362):
            for i in range(2): f.var('output', f.var('Comp', index=i, width=1), i, 1)
            second(f, t, 'DefrostProcess')
        record(f'DEF-DISABLE-{label}-CURRENT', '4/4.4/禁用清理复核', f.var('PSC316DefrostState'), 0)

    # Emergency is not itself Comp1Err/Comp2Err, unlike ordinary unit faults.
    f = defrost()
    f.p(1406, 1)
    for t in range(1, 362):
        second(f, t, 'DefrostProcess')
        f.call('ErrorProcess')
        f.call('IoOutAction')
    record('DEF-EMERGENCY-361', '4.4/内外机生命周期一致性',
           [f.var('output', index=i, width=1) for i in range(2)] + [f.p(1420), f.p(1421)], [0, 0, 0, 0])

    for pressure, ticks, want, label in ((3800, 30, 0, 'EQ38'), (3801, 19, 0, 'BEFORE2S'), (3801, 20, 1, 'AT2S')):
        f = base()
        f.p(1443, pressure)  # PLCREADPara+23 high pressure 1
        f.var('uc100ms', 1)
        for _ in range(ticks): f.call('CompErrAction')
        record(f'HP-{label}', '4.6.4', f.p(606), want)

    f = base()
    running(f)
    f.p(613, 1)
    f.call('ErrorProcess')
    record('SENSOR-FIN1-SYSTEM-STOP', '4.6.2',
           [f.var('Comp', index=i, width=1) for i in range(2)], [0, 1])
    f = base()
    running(f)
    f.p(612, 1)
    f.call('ErrorProcess')
    record('SENSOR-AMBIENT-UNIT-STOP', '4.6.3',
           [f.var('Comp', index=i, width=1) for i in range(2)], [0, 0])

    f = base()
    f.p(54, 150)
    f.p(1444, 300)
    f.var('CompRunTime', 1000, 0, 4)
    f.var('EnableCheckLow', 1, 0, 4)
    f.var('X01_En', 1)
    f.var('uc100ms', 1)
    for _ in range(49): f.call('CompErrAction')
    before = f.p(600)
    f.call('CompErrAction')
    at5 = f.p(600)
    f.var('X01_En', 0)
    f.call('CompErrAction')
    record('LP-5S-AUTO-RECOVERY', '4.6.5', [before, at5, f.p(600)], [0, 1, 0])

    f = base(1)
    f.var('FinTemp', -60, 0, 2)
    running(f, 1, 0)
    f.var('CompRunTime', 601, 0, 4)
    f.var('DefGapCount', 1801, 0, 4)
    for t in range(1, 60): second(f, t, 'DefEnable')
    before = f.var('DefComp0', index=0, width=4)
    second(f, 60, 'DefEnable')
    record('DEF-NORMAL-60S-ENTRY', '4.4', [before, f.var('DefComp0', index=0, width=4)], [0, 1])

    f = base(1)
    history = []
    for temperature in (69, 70, 120, 121, 100, 69):
        f.p(1422, temperature)
        for t in range(1, 31): second(f, t, 'OutdoorHeatFanStageUpdate')
        history.append(f.var('OutdoorHeatTwoFan'))
    record('HEAT-FAN-Z-ZD-HYSTERESIS', '4.3.2', history, [1, 1, 1, 0, 0, 1])

    for manual in (0, 1):
        f = base()
        f.p(167, 1)
        f.p(1300, manual)
        f.p(1302, 1)
        f.p(1303, 1)
        running(f)
        f.call('OutdoorUnitAction')
        f.call('HandDebugY02Ctrl')
        f.call('OutdoorProtectOutputLimit')
        record(f'DISABLE-FINAL-OUTPUT-MANUAL{manual}', '4/禁用',
               [f.var('output', index=i, width=1) for i in range(2)], [0, 0])

    f = base(1)
    f.p(193, 60)
    f.p(41, 30)
    f.call('OutdoorUnitAction')
    record('FOURWAY-GATEWAY193-OVERRIDE', '4.5/接口写入效果', [f.p(41), f.p(193)])

    f = Firmware(IN)
    f.p(214, 5)
    f.field(False, 1, 'CanDefrost', value=7)
    f.field(False, 2, 'CanDefrost', value=1)
    f.call('PSC316UpdateDefrostOwner')
    record('INDOOR-RECOVERY-KEEPS-OWNER', '4.4/跨机互斥', f.var('PSC316DefrostOwner'), 1)
    f.field(False, 1, 'CanDefrost', value=0)
    f.call('PSC316UpdateDefrostOwner')
    record('INDOOR-COMPLETE-RELEASES-OWNER', '4.4/跨机互斥', f.var('PSC316DefrostOwner'), 2)

    f = Firmware(IN)
    f.p(327, 1)
    f.var('PSC316SetValid', 1, 0, 1)
    for j, value in ((5, 150), (6, 180)):
        f.var('PSC316SetMirror', value, j, 2)
    f.call('PSC316SharedMirrorFromUnit1')
    record('FULLFRESH-SHARED-FIRST-SEED', '4.1/全新风默认值', [f.p(1331), f.p(1332)], [220, 100])

    DEST.mkdir(parents=True, exist_ok=True)
    report = dict(date='2026-11-09', mode='offline ARM function/handler execution only',
                  serial_or_probe_access=False, hardware_tested=False, firmware_modified=False,
                  artifacts={str(p.relative_to(ROOT)): sha(p) for p in (OUT, IN)},
                  source_inventory_count=len(manifest['source_inventory']), source_mismatches=changes,
                  input_conversion_hook='FAN cases stub OutdoorCondTempMax only; other cases inject RAM inputs',
                  counters=dict(Counter(r['status'] for r in results)), results=results)
    (DEST/'arm_spec_observations.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['counters'], ensure_ascii=False))
    for r in results:
        if r['status'] != 'PASS': print(json.dumps(r, ensure_ascii=False))


if __name__ == '__main__':
    main()
