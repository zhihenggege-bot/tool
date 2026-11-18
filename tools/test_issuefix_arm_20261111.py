"""Run current compiled ARM code; no serial port or debugger is opened."""
import hashlib
import inspect
import json
from collections import Counter

from test_defrost_lifecycle_arm import Firmware, ROOT
import review_three_issues_offline_20261111 as old
from test_shared_type_arm_20261110 import hooks, hmi, rtu
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR

PACKAGE = ROOT / '.codex-tmp/issuefix_v1059_v1241_20261111'
DEST = ROOT / '测试证据/修复回归_20261111'
ROWS = []
PROFILE = 'PRODUCTION'


def image(which):
    model, version = ('330', '10.59') if which == 'indoor' else ('316', '12.41')
    return Firmware(PACKAGE / PROFILE / f'PSC{model}_V{version}_{PROFILE}.axf')


def check(name, observed, expected):
    row = dict(profile=PROFILE, name=name, observed=observed, expected=expected,
               passed=observed == expected)
    ROWS.append(row)
    assert row['passed'], row


def pages():
    f = image('indoor')
    f.p(214, 3)
    hooks(f, ('StartUart1SendData',))
    for u in (1, 2):
        f.var('ReadBackFlag', 1, u, 2)
    for u in (1, 2, 1, 2):
        f.p(540, u)
        for offset in range(4):
            f.p(881 + offset, offset + 1)
        f.call('PSC316PageSync')
        f.call('PSC316PageSync')
        check(f'page{u}/diagnostics-retained', [f.p(n) for n in range(881, 885)], [1, 2, 3, 4])
        check(f'page{u}/no-spurious-eev-job', old.job(f)['active'], 0)
    for a in range(881, 885):
        hmi(f, a, [99])
        check(f'FC06/diagnostic{a}-readonly', f.p(a), a - 880)
    hmi(f, 881, [50, 1, 60, 1], True)
    check('FC16/diagnostics-readonly', [f.p(n) for n in range(881, 885)], [1, 2, 3, 4])
    f.p(740, 5)
    f.call('PSC316PageSync')
    check('legacy-calibration-preserved', [old.job(f)[n] for n in ('active', 'address', 'values')], [1, 1580, [5]])
    f = image('indoor')
    f.p(214, 3)
    for i in range(4):
        f.var('PSC316EevManRelease', 0, i, 1)
    # Existing formal manual EEV bridge still accepts and forwards to its unit.
    for unit in (1, 2):
        f.var('PSC316WriteJob', 0, width=1)
        f.p(220 + (unit - 1) * 4, 123)
        f.p(221 + (unit - 1) * 4, 1)
        f.call('PSC316Gateway_EevManService')
        j = old.job(f)
        check(f'eev-bridge/unit{unit}', [j['active'], j['unit'], j['address']], [1, unit, 155])
        # Mark prior unit serviced to permit the following fixture.
        for i in range(4):
            f.var('PSC316EevManSent', f.p(220 + (unit - 1) * 4 + i), (unit - 1)*4+i, 2)


def receive(f, response):
    f.uc.mem_write(f.symbols['ucUart5Buff'][0], response)
    f.var('ucUart5ReceLen', len(response))
    f.call('ModuleReciData')
    f.var('Systick_1ms', f.var('Systick_1ms') + 10)
    f.call('ModuleReciData')


def polling(unit_count=2):
    f = image('indoor')
    f.uc.mem_map(0x22000000, 0x100000)
    f.p(214, unit_count + 1)
    f.p(540, 1)
    for i in range(4):
        f.var('PSC316VersionRequestPending', 0, i, 1)
    sent = []
    def driver(uc, address, size, user):
        if address == f.symbols['StartUart5SendData'][0] & ~1:
            sent.append(bytes(uc.mem_read(f.symbols['ucUart5Buff'][0], f.var('ucUart5SendLen'))))
            # Execute the same context capture at the same phase as real UART.
            uc.reg_write(UC_ARM_REG_PC, f.symbols['PSC316Gateway_NoteTransmit'][0])
        else:
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    for name in ('StartUart5SendData', 'UART5Init'):
        a = f.symbols[name][0] & ~1
        f.uc.hook_add(UC_HOOK_CODE, driver, begin=a, end=a)
    trace = []
    requests = Counter()
    for cycle in range(650 if unit_count == 2 else 1100):
        f.var('Systick_1ms', 10000 + cycle * 100)
        # A stream of failed manual writes, with actual mismatching readbacks.
        if not old.job(f)['active']:
            f.call('PSC316Gateway_LegacyEEVWrite', 1, 0, 4)
        before = len(sent)
        f.call('ModuleSendData')
        if len(sent) == before:
            continue
        frame = sent[-1]
        unit, fn = frame[:2]
        address = int.from_bytes(frame[2:4], 'big')
        count = int.from_bytes(frame[4:6], 'big')
        requests[(unit, fn, address)] += 1
        if unit >= 254:
            continue
        if fn in (6, 16):
            response = rtu(frame[:6])
        else:
            data = [0] * count
            # A sensor fault is present on each outdoor unit, independent of page.
            for register, value in ((615, 1), (1471, 0x8000), (1501, 4)):
                if address <= register < address + count:
                    data[register-address] = value
            response = rtu(bytes([unit, 3, count * 2]) + b''.join(v.to_bytes(2, 'big') for v in data))
        receive(f, response)
        f.call('PSC316Gateway_PublishToHMI')
        trace.append(dict(cycle=cycle, unit=unit, function=fn, address=address,
                          write_phase=old.job(f)['phase']))
    for unit in range(1, unit_count + 1):
        for address in (600, 664, 1420, 1460, 1522, 1602, 165, 1528):
            check(f'continuous-failed-writes/unit{unit}/poll{address}', requests[(unit, 3, address)] >= 2, True)
        check(f'continuous-failed-writes/unit{unit}/sensor-mirror', f.p(2022+(unit-1)*128+15), 1)
        check(f'continuous-failed-writes/unit{unit}/layer', f.p(2598+unit-1), 4)
    check('stress/failed-writes-exercised', requests[(1, 6, 155)] >= 8, True)
    (DEST / f'poll_trace_{PROFILE}_{unit_count}units.json').write_text(json.dumps(trace, indent=2)+'\n', 'utf8')
    # Urgency must discard an interrupted position so no old poll is resurrected.
    f.var('PSC316PollResume', 5, 0, 1)
    f.var('PSC316PollPreempted', 1, 0, 1)
    f.var('PSC316WriteJob', 0, width=1)
    f.var('PSC316BusActive', 0)
    f.var('ModuleNum', 1)
    # Default urgency is 0; mark old shadow1 to trigger the real reset branch.
    f.var('OLD_UnitWriteStatusUrgencyStop', 1)
    f.call('ModuleSendData')
    check(f'urgency/{unit_count}units/resume-cleared', f.var('PSC316PollResume', index=0, width=1), 255)


def polling_four_units():
    polling(4)


def heating():
    old.image = image
    for fan_type in (1, 3, 4):
        f = old.heat_fixture(fan_type)
        timeline = []
        for elapsed in range(0, 45001, 100):
            f.var('Systick_1ms', 100000 + elapsed)
            f.var('uc1s', int(elapsed % 1000 == 0))
            f.call('OutdoorFanUpdateTimers')
            f.call('OutdoorFanHeatPump')
            if f.p(874) and not timeline:
                timeline.append(elapsed)
        gap = 15000 if PROFILE == 'PRODUCTION' else 3000
        check(f'heat/type{fan_type}/both-fans', [f.p(872), f.p(874)], [1, 1])
        check(f'heat/type{fan_type}/second-fan-gap', timeline[0], gap)
        if fan_type == 3:
            check('heat/type3/high-speed', f.var('OutdoorTypeIIFan2High'), 1)
    # Ambient target holds are unchanged, including equality/deadband.
    for temp, initial, expected in ((69, 0, 1), (70, 0, 0), (120, 1, 1), (121, 1, 0)):
        f = old.heat_fixture()
        f.var('OutdoorHeatTwoFan', initial)
        f.p(1422, temp)
        f.var('uc1s', 1)
        for _ in range(29):
            f.call('OutdoorHeatFanStageUpdate')
        check(f'heat/{temp}/before30', f.var('OutdoorHeatTwoFan'), initial)
        f.call('OutdoorHeatFanStageUpdate')
        check(f'heat/{temp}/at30', f.var('OutdoorHeatTwoFan'), expected)


def recover():
    f = image('outdoor')
    for a, v in {1:0,165:1,166:3,172:300,173:150,179:30,180:30}.items():
        f.p(a, v)
    pressures = {}
    for p in range(800, 2000):
        t = f.call('OutdoorPTTempFromPressure', p)
        if 340 <= t <= 360:
            pressures.setdefault('mid', p)
        if 420 < t < 500:
            pressures.setdefault('high', p)
    f.var('OutdoorTypeIILowFanOff', 1)
    f.var('uc1s', 1)
    f.var('output', 1, 0, 1)
    def step(env, key, seconds):
        f.p(1422, env)
        f.p(1443, pressures[key])
        f.p(1445, pressures[key])
        for _ in range(seconds):
            f.var('Systick_1ms', f.var('Systick_1ms') + 1000)
            f.call('OutdoorFanTypeII')
    step(110, 'mid', 15)
    step(90, 'high', 15)
    check('stage1/alternating15+15/no-merged-recovery', f.var('OutdoorTypeIILowFanOff'), 1)
    step(90, 'high', 14)
    check('stage1/cond29/no-recovery', f.var('OutdoorTypeIILowFanOff'), 1)
    step(90, 'high', 1)
    check('stage1/cond30/recovery', f.var('OutdoorTypeIILowFanOff'), 0)
    f.var('OutdoorTypeIILowFanOff', 1)
    step(110, 'mid', 29)
    check('stage1/env29/no-recovery', f.var('OutdoorTypeIILowFanOff'), 1)
    step(110, 'mid', 1)
    check('stage1/env30/recovery', f.var('OutdoorTypeIILowFanOff'), 0)
    f.call('OutdoorFanResetAlgorithmState')
    check('stage1/reset-independent-counters',
          [f.var(n) for n in ('OutdoorTypeIILowRecoverCount','OutdoorTypeIILowRecoverEnvCount','OutdoorTypeIILowRecoverCondCount')], [0,0,0])


def timing():
    # Reuse the old measurement fixture, removing only its OLD-result assertions.
    source = inspect.getsource(old.minimum_run_observations)
    source = source.replace("    assert [r['offline_elapsed_seconds'] for r in phase600] == [14.4, 29.4, 59.4, 119.4, 299.4]\n", '')
    source = source.replace("    assert all(0 <= r['shortfall_seconds'] <= 1 for r in rows)\n", '')
    scope = dict(old.__dict__, image=image)
    exec(compile(source, 'new_minimum_run_fixture', 'exec'), scope)
    result = scope['minimum_run_observations']()
    for row in result['rows']:
        check(f"min-run/{row['setting_seconds']}/phase{row['start_phase_ms']}/no-early-stop",
              row['offline_elapsed_seconds'] >= row['setting_seconds'], True)
        check(f"min-run/{row['setting_seconds']}/phase{row['start_phase_ms']}/bounded-late-stop",
              row['offline_elapsed_seconds'] <= max(row['setting_seconds'] + .2, 16), True)
    for row in result['millisecond_guard_checks']:
        check(f"{row['kind']}/wrap{row['start_tick']}/{row['elapsed_ms']}",
              row['allowed'], int(row['elapsed_ms'] >= 300000))
    result['status'] = 'CURRENT_IMAGE_NO_EARLY_RELEASE'
    result['scope'] = 'Virtual 100ms scan, 10 phase offsets; no board wall-clock measurement'
    (DEST / f'minimum_timing_{PROFILE}.json').write_text(json.dumps(result, indent=2)+'\n','utf8')


def main():
    global PROFILE
    DEST.mkdir(parents=True, exist_ok=True)
    try:
        for PROFILE in ('PRODUCTION', 'BENCH_ONLY_3S'):
            manifest = json.loads((PACKAGE / PROFILE / 'manifest.json').read_text('utf8'))
            assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in manifest['source_inventory'].items())
            assert all(hashlib.sha256((PACKAGE/PROFILE/p).read_bytes()).hexdigest()==h for p,h in manifest['artifacts'].items())
            for test in (pages, polling, polling_four_units, heating, recover, timing):
                print(PROFILE, test.__name__, flush=True)
                test()
    finally:
        (DEST/'focused_arm_results.json').write_text(json.dumps(dict(hardware_access=False,
            passed=sum(r['passed'] for r in ROWS),total=len(ROWS),rows=ROWS), ensure_ascii=False,indent=2)+'\n','utf8')
    print(len(ROWS), 'ARM checks passed', flush=True)


if __name__ == '__main__':
    main()
