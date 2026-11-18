"""Offline reproduction on exact loaded ARM image; never opens a bench device."""
import json
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware, ROOT

BUILD = ROOT / '.codex-tmp/vfd_scale_v1242_20261112'
DEST = ROOT / '测试证据/四项复核_20261112/restart_watchdog_ARM_reproduction.json'


def main():
    rows = []
    for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
        for stop in (30, 60, 120, 300):
            f = Firmware(BUILD / profile / f'PSC330_V10.59_{profile}.axf')
            f.p(45, 15)
            f.p(1830 + 15, stop)  # Unit1's actual setting mirror:316[180].
            f.field(True, 1, 'CompControl', 0, 1)
            f.field(False, 1, 'CompStatus', 0, 0)
            f.var('Systick_1ms', 1000)
            f.call('CompStartStateUpdate')
            f.var('Systick_1ms', 75999)
            f.call('CompStartStateUpdate')
            assert f.field(True, 1, 'CompControl', 0) == 1
            f.var('Systick_1ms', 76000)
            f.call('CompStartStateUpdate')
            withdrawn = f.field(True, 1, 'CompControl', 0) == 0
            retry = f.var('CompStartRetryUntil', index=2, width=8)
            assert withdrawn and retry == 376000
            rows.append(dict(profile=profile, fan_min_stop_s=stop,
                             indoor_fan_prestart_s=15,
                             request_withdrawn_at_elapsed_s=75,
                             retry_inhibit_s=300,
                             ignores_outdoor_min_stop=True,
                             reproduced=True))
    DEST.write_text(json.dumps(dict(hardware_access=False, firmware='330 V10.59',
        interpretation='A reproduction of withdrawal, not acceptance of the behavior',
        rows=rows), ensure_ascii=False, indent=2), encoding='utf8')
    print(len(rows), 'watchdog withdrawal reproductions confirmed')


if __name__ == '__main__':
    main()
