"""Reproduce three observations in pinned ARM images; no hardware access.

This is an observation harness, not an acceptance run or a firmware fix.
All synthetic fixtures and time advances are confined to Unicorn RAM.
"""
import hashlib
import json
import struct
from pathlib import Path

from test_defrost_lifecycle_arm import Firmware, ROOT

PACKAGE = ROOT / '.codex-tmp/shared_type_v1058_20261110/BENCH_ONLY_3S'
DEST = ROOT / '测试证据/台架执行_20261111/三项问题_当前ARM离线复现.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image(which):
    name = 'PSC330_V10.58' if which == 'indoor' else 'PSC316_V12.40'
    return Firmware(PACKAGE / (name + '_BENCH_ONLY_3S.axf'))


def job(f):
    address, size = f.symbols['PSC316WriteJob']
    active, phase, unit, retry, count, target, *values = struct.unpack(
        '<BBBBHH10h', bytes(f.uc.mem_read(address, size)))
    return dict(active=active, phase=phase, unit=unit, retry=retry,
                count=count, address=target, values=values[:count])


def page_alias():
    f = image('indoor')
    # ModuleNumSet is internal214 (count including330), not HMI388.
    f.p(214, 3)
    f.p(540, 1)
    for unit in (1, 2):
        f.var('ReadBackFlag', 1, unit, 2)
    f.call('PSC316PageSync')
    assert f.var('PSC316PageLoaded') == 1
    before = job(f)
    f.p(881, 4)  # Simulate IndoorTargetCompDisp producer, NOT a user edit.
    f.call('PSC316PageSync')
    after = job(f)
    assert after == dict(active=1, phase=1, unit=1, retry=0,
                         count=1, address=155, values=[4])
    # Reproduce requeue after a prior job is retired; not a serial simulation.
    address, size = f.symbols['PSC316WriteJob']
    f.uc.mem_write(address, bytes(size))
    f.call('PSC316PageSync')
    requeued = job(f)
    assert requeued == after
    # A page load also overwrites the diagnostic shared with the old EEV field.
    f.uc.mem_write(address, bytes(size))
    f.p(540, 2)
    f.call('PSC316PageSync')
    after_page_change = dict(diagnostic881=f.p(881), job=job(f))
    assert after_page_change['diagnostic881'] == 0
    return dict(status='REPRODUCED_CODE_DEFECT', before=before,
                diagnostic881_generated_job=after, requeued=requeued,
                after_legal_page_change=after_page_change,
                scope='Real PSC316PageSync and gateway enqueue; no RTU timing emulation')


def sensor_publish():
    f = image('outdoor')
    f.var('BoardAddressSet', 1)
    for address, value in {1: 1, 107: 1, 165: 1, 166: 3, 615: 1}.items():
        f.p(address, value)
    f.call('ErrorProcess')
    row = dict(raw615=f.p(615), packed1471=f.p(1471), layer1501=f.p(1501))
    assert row == dict(raw615=1, packed1471=32768, layer1501=4)
    return dict(status='PUBLISHER_SUBSCOPE_OK', observed=row,
                scope='Already-established NTC3 fault fixture; not sensor detection, serial delivery, or HMI screen acceptance')


def heat_fixture(fan_type=3):
    f = image('outdoor')
    for address, value in {1: 1, 107: 1, 165: 1 if fan_type == 3 else 0,
                           166: fan_type, 174: 70, 175: 50, 176: 50,
                           179: 30, 180: 30, 872: 1, 874: 0, 1422: 69}.items():
        f.p(address, value)
    f.var('OutdoorHeatTwoFan', 1)
    return f


def heat_two_fans():
    f = heat_fixture()
    scratch = 0x20060000
    f.var('Systick_1ms', 100000)
    f.call('OutdoorFanUpdateTimers')
    f.var('Systick_1ms', 104000)  # BENCH action interval3s has elapsed.
    f.call('OutdoorFanSelectTwoSequential', scratch, scratch + 1)
    first_selection = list(f.uc.mem_read(scratch, 2))
    assert first_selection == [1, 1]
    # The caller has not published the selected fan state yet. Its second
    # apply sees the just-updated action timestamp and returns old state.
    f.call('OutdoorTypeIIFanApply', 1, 1, 1, scratch, scratch + 1)
    after_second_apply = dict(selected=list(f.uc.mem_read(scratch, 2)),
                              published=[f.p(872), f.p(874)])
    assert after_second_apply['published'] == [1, 0]
    timeline = []
    f = heat_fixture()
    for elapsed in range(0, 60001, 100):
        f.var('Systick_1ms', 100000 + elapsed)
        f.var('uc1s', int(elapsed % 1000 == 0))
        f.call('OutdoorFanUpdateTimers')
        f.call('OutdoorFanHeatPump')
        assert [f.p(872), f.p(874)] == [1, 0]
        if elapsed % 5000 == 0:
            timeline.append(dict(elapsed_ms=elapsed, fan_commands=[f.p(872), f.p(874)],
                                 two_fan_target=f.var('OutdoorHeatTwoFan'),
                                 stage=f.var('OutdoorFanStage'),
                                 change_seconds=f.var('OutdoorFanChangeSeconds')))
    control = heat_fixture(1)
    for elapsed in range(0, 5001, 100):
        control.var('Systick_1ms', 100000 + elapsed)
        control.var('uc1s', int(elapsed % 1000 == 0))
        control.call('OutdoorFanUpdateTimers')
        control.call('OutdoorFanHeatPump')
    assert [control.p(872), control.p(874)] == [1, 1]
    return dict(status='REPRODUCED_CODE_DEFECT', first_selection=first_selection,
                after_second_apply=after_second_apply, timeline=timeline,
                two_fixed_fan_control=[control.p(872), control.p(874)],
                scope='Steady heat controller and fan timers in ARM image; input target already satisfied; no physical relays')


def minimum_run_observations():
    rows = []
    for setting, start_phase in [(s, phase) for s in (10, 30, 60, 120, 300)
                                  for phase in range(0, 1000, 100)]:
        f = image('outdoor')
        for address, value in {1: 1, 107: 1, 165: 2, 166: 4, 179: setting,
                               180: 30, 872: 1, 874: 1}.items():
            f.p(address, value)
        for name, value in {'OutdoorFanLastWorkMode': 1, 'OutdoorFanLastUnitType': 2,
                            'OutdoorFanLastType': 4, 'OutdoorFanLastPressureMode': 1}.items():
            f.var(name, value)
        stopped = None
        for elapsed in range(0, (setting + 30) * 1000, 100):
            tick = 100000 + start_phase + elapsed
            f.var('Systick_1ms', tick)
            f.var('uc1s', int(tick % 1000 == 0))
            f.call('OutdoorBoardFanControl')
            if not f.p(872) and not f.p(874):
                stopped = elapsed / 1000
                break
        assert stopped is not None
        rows.append(dict(setting_seconds=setting, start_phase_ms=start_phase,
                         offline_elapsed_seconds=stopped,
                         signed_difference_seconds=round(stopped - setting, 3),
                         shortfall_seconds=round(max(0, setting - stopped), 3)))
    phase600 = [r for r in rows if r['start_phase_ms'] == 600]
    assert [r['offline_elapsed_seconds'] for r in phase600] == [14.4, 29.4, 59.4, 119.4, 299.4]
    assert all(0 <= r['shortfall_seconds'] <= 1 for r in rows)
    guards = []
    for stamp in (100600, 0xFFFFF000):
        f = image('outdoor')
        f.p(179, 300)
        f.p(180, 300)
        for kind in ('Run', 'Stop'):
            f.var('OutdoorFan' + kind + 'Tick', stamp, 0, 4)
            f.var('OutdoorFan' + kind + 'TickValid', 1, 0, 1)
            for elapsed in (299999, 300000):
                f.var('Systick_1ms', stamp + elapsed)
                observed = f.call('OutdoorFan' + kind + 'Ok', 0)
                assert observed == int(elapsed >= 300000)
                guards.append(dict(kind=kind, start_tick=stamp, elapsed_ms=elapsed, allowed=observed))
    return dict(status='QUANTIZATION_REPRODUCED_USER_ACCEPTED_OLD_30S_RESULT', rows=rows,
                per_setting_summary=[dict(setting_seconds=s,
                    minimum_elapsed_seconds=min(r['offline_elapsed_seconds'] for r in rows if r['setting_seconds'] == s),
                    maximum_elapsed_seconds=max(r['offline_elapsed_seconds'] for r in rows if r['setting_seconds'] == s),
                    maximum_shortfall_seconds=max(r['shortfall_seconds'] for r in rows if r['setting_seconds'] == s))
                    for s in (10, 30, 60, 120, 300)],
                millisecond_guard_checks=guards,
                fixture='Both fan commands turn on at fixture start; no compressor; normal no-compressor delay also applies',
                scope='Virtual100ms scan and1s phase; no wall-clock board measurement. 10s is masked by normal15s stop delay. Millisecond run guard is not used by this all-off branch.')


def type_ii_recovery_or():
    f = image('outdoor')
    for address, value in {1: 0, 165: 1, 166: 3, 172: 300, 173: 150,
                           179: 30, 180: 30}.items():
        f.p(address, value)
    pressures = {}
    for pressure in range(1000, 1601):
        temperature = f.call('OutdoorPTTempFromPressure', pressure)
        if 340 <= temperature <= 360:
            pressures.setdefault('mid', (pressure, temperature))
        if temperature > 420:
            pressures.setdefault('high', (pressure, temperature))
        if len(pressures) == 2:
            break
    assert len(pressures) == 2
    f.var('OutdoorTypeIILowFanOff', 1)
    f.var('uc1s', 1)
    f.var('output', 1, 0, 1)
    rows = []
    for label, ambient, pressure_key in [('env_only', 110, 'mid'), ('cond_only', 90, 'high')]:
        pressure, temperature = pressures[pressure_key]
        f.p(1422, ambient)
        f.p(1443, pressure)
        f.p(1445, pressure)
        for second in range(15):
            f.var('Systick_1ms', 100000 + len(rows) * 15000 + second * 1000)
            f.call('OutdoorFanTypeII')
        rows.append(dict(label=label, ambient10=ambient, condensation10=temperature,
                         duration_seconds=15, recovery_count=f.var('OutdoorTypeIILowRecoverCount'),
                         low_off=f.var('OutdoorTypeIILowFanOff')))
    assert [r['low_off'] for r in rows] == [1, 0]
    return dict(status='REPRODUCED_SPEC_MISMATCH', observations=rows,
                expected='Neither independent condition has held30s; low-off latch should remain1',
                scope='Real ARM cooling controller, initialized low-off fixture; this checks latch reset, not terminal restart timing')


def main():
    manifest = json.loads((PACKAGE / 'manifest.json').read_text('utf-8-sig'))
    mismatches = [name for name, expected in manifest['source_inventory'].items()
                  if sha(ROOT / name) != expected]
    assert not mismatches, mismatches
    images = sorted(PACKAGE.glob('*.axf'))
    for path in images:
        assert sha(path) == manifest['artifacts'][path.name], path
    report = dict(client_date='2026-11-11', hardware_access=False, firmware_modified=False,
                  evidence_kind='PINNED_ARM_OFFLINE_OBSERVATIONS',
                  source_mismatches=mismatches,
                  source_inventory_count=len(manifest['source_inventory']),
                  artifacts={p.name: sha(p) for p in images},
                  page_alias=page_alias(), sensor_publish=sensor_publish(),
                  heating=heat_two_fans(), timing=minimum_run_observations(),
                  type_ii_recovery_or=type_ii_recovery_or())
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(evidence=str(DEST.relative_to(ROOT)), hardware_access=False,
                          statuses={k:report[k]['status'] for k in ('page_alias','sensor_publish','heating','timing','type_ii_recovery_or')}), ensure_ascii=False))


if __name__ == '__main__':
    main()
