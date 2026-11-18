"""Actual330 ARM regression for outdoor ambient isolation; no hardware access."""
import hashlib
import json
from test_defrost_lifecycle_arm import Firmware, ROOT

PACKAGE = ROOT / '.codex-tmp/ambient_scope_v1061_20261112'
DEST = ROOT / '测试证据/环境联锁修复_20261112'
ROWS = []


def check(profile, label, got, want):
    row = dict(profile=profile, label=label, got=got, want=want, passed=got == want)
    ROWS.append(row)
    assert row['passed'], row


def fixture(profile, mode=1, units=2):
    f = Firmware(PACKAGE / profile / f'PSC330_V10.61_{profile}.axf')
    for address, value in {1: mode, 236: mode, 99: 1, 214: units + 1,
                           709: 2, 278: 0, 279: 600, 280: -120, 281: 350}.items():
        f.p(address, value)
    for unit in range(1, units + 1):
        f.var('PSC316SetValid', 1, unit - 1, 1)
        f.field(False, unit, 'AII', 4, 155)
        for comp in (0, 1):
            f.p(250 + (unit - 1) * 2 + comp, 1)
            f.field(False, unit, 'CompStatus', comp, 3 if mode else 2)
            f.field(True, unit, 'CompControl', comp, 1)
            f.var('CompMinRunCount', 1000, 2 * unit + comp, 4)
            f.var('CompMinStopCount', 1000, 2 * unit + comp, 4)
    f.var('Systick_1ms', 100000)
    return f


def requests(f, unit):
    return [f.field(True, unit, 'CompControl', c) for c in (0, 1)]


def isolation(profile):
    for mode in (0, 1):
        for faulty in (1, 2):
            peer = 3 - faulty
            f = fixture(profile, mode)
            f.field(False, faulty, 'AII', 4, 9999)
            f.p(2598 + faulty - 1, 0x30)  # Own environment + unit fault.
            for c in (0, 1):
                f.field(False, faulty, 'CompStatus', c, 1)
            f.p(737, 1)  # A stale global latch must not keep a healthy peer off.
            for tick in (100000, 140000):
                f.var('Systick_1ms', tick)
                f.call('DeviceStatusCount')
                f.call('CompMainAction')
            label = f'mode{mode}/faulty{faulty}'
            check(profile, label + '/peer-requests-retained', requests(f, peer), [1, 1])
            check(profile, label + '/faulted-requests-retired', requests(f, faulty), [0, 0])
            check(profile, label + '/not-global', f.p(737), 0)
            check(profile, label + '/faulted-ineligible', f.call('CompCanParticipate', faulty, 0), 0)
            check(profile, label + '/peer-eligible', f.call('CompCanParticipate', peer, 0), 1)
            # Capacity loading remains possible on the healthy peer.
            for c in (0, 1):
                f.field(False, peer, 'CompStatus', c, 0)
                f.field(True, peer, 'CompControl', c, 0)
            f.p(707, 1)
            f.var('Systick_1ms', 200000)
            f.call('CompMainAction')
            check(profile, label + '/healthy-loads-one', sum(requests(f, peer)), 1)


def summary(profile):
    # Exercise all16 masks across4 configured outdoor units.
    f = fixture(profile, units=4)
    for mask in range(16):
        for unit in range(1, 5):
            f.p(2598 + unit - 1, 0x20 if mask & (1 << (unit - 1)) else 0)
        check(profile, f'summary/mask{mask}', f.call('CompAllOutdoorAmbientBlocked'), int(mask == 15))
    f.var('UnitCommErr', 1, 2, 2)
    check(profile, 'summary/communication-is-not-ambient-proof', f.call('CompAllOutdoorAmbientBlocked'), 0)
    f.var('UnitCommErr', 0, 2, 2)
    f.p(1832 + 48, 1)  # Disable unit2; its ambient word no longer counts.
    f.p(2599, 0)
    check(profile, 'summary/disabled-unit-excluded', f.call('CompAllOutdoorAmbientBlocked'), 1)
    f.p(214, 1)
    check(profile, 'summary/no-outdoor-not-an-alarm', f.call('CompAllOutdoorAmbientBlocked'), 0)
    f = fixture(profile)
    f.p(2598, 0x20); f.p(2599, 0x20)
    f.p(236, 2)
    check(profile, 'summary/ventilation-no-ambient-alarm', f.call('CompAllOutdoorAmbientBlocked'), 0)
    f.p(236, 1); f.p(99, 0)
    check(profile, 'summary/no-heatpump-no-ambient-alarm', f.call('CompAllOutdoorAmbientBlocked'), 0)


def guards(profile):
    f = fixture(profile, mode=0)
    f.field(False, 1, 'AII', 4, -20)
    f.call('CompMainAction')
    check(profile, 'valid-low-temperature-does-not-override316', requests(f, 2), [1, 1])
    check(profile, 'valid-low-temperature-no-global-latch', f.p(737), 0)
    f.p(2598, 0x20)
    f.field(False, 1, 'CompStatus', 0, 0)
    f.field(True, 1, 'CompControl', 0, 0)
    check(profile, 'own-ambient-block-still-prevents-load', f.call('CompCanLoad', 1, 0), 0)
    f.p(2598, 0)
    f.var('CompMinStopCount', 0, 2, 4)
    check(profile, 'minimum-stop-still-prevents-load', f.call('CompCanLoad', 1, 0), 0)
    f.var('CompMinStopCount', 1000, 2, 4)
    f.field(False, 1, 'CanDefrost', 0, 8)
    check(profile, 'defrost-still-prevents-load', f.call('CompCanLoad', 1, 0), 0)
    f.field(False, 1, 'CanDefrost', 0, 0)
    f.var('UnitCommErr', 1, 1, 2)
    check(profile, 'communication-still-prevents-load', f.call('CompCanLoad', 1, 0), 0)
    f.var('UnitCommErr', 0, 1, 2)
    f.p(1832, 1)
    check(profile, 'disable-still-prevents-load', f.call('CompCanLoad', 1, 0), 0)
    f = fixture(profile)
    f.var('CompMinRunCount', 0, 4, 4)
    check(profile, 'minimum-run-still-prevents-unload', f.call('CompCanUnload', 2, 0), 0)
    f.var('CompActionTickValid', 1)
    f.var('CompLastActionTick', 100000)
    f.p(707, 2)
    f.call('CompMainAction')
    check(profile, 'action-interval-still-holds-all', [requests(f, u) for u in (1, 2)], [[1, 1], [1, 1]])


def main():
    DEST.mkdir(exist_ok=True)
    hashes = {}
    for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
        m = json.loads((PACKAGE / profile / 'manifest.json').read_text('utf8'))
        assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
                   for p, h in m['source_inventory'].items())
        for name, digest in m['artifacts'].items():
            assert hashlib.sha256((PACKAGE / profile / name).read_bytes()).hexdigest() == digest
            hashes[f'{profile}/{name}'] = digest
        isolation(profile)
        summary(profile)
        guards(profile)
    result = dict(hardware_access=False, method='Actual ARM functions with synthetic RAM feedback',
                  total=len(ROWS), passed=sum(r['passed'] for r in ROWS), rows=ROWS, artifact_hashes=hashes)
    (DEST / 'ambient_scope_ARM_results.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(result['passed'], '/', result['total'], 'ambient scope ARM checks passed')


if __name__ == '__main__':
    main()
