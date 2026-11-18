"""V10.51 raw ADC -> latched sensor fault -> load-stop aggregation, offline only."""
import json
from test_ai3_hold_reason_arm_20261105 import board, PACKAGE


def main():
    rows = []
    for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
        for mode in (0, 1, 2):
            for electrical_type in (0, 1):
                for bad_raw in (0, 4095):
                    f = board(profile, mode)
                    f.p(462, electrical_type)
                    f.var('uc10ms', 1)
                    f.var('uc100ms', 1)
                    for i in range(8):
                        f.var('ADC_Val', 2000, i, 2)
                    for _ in range(20):
                        f.call('ADProcess')
                    assert f.var('SensorStatus', index=3, width=1) == 0
                    f.var('ADC_Val', bad_raw, 6, 2)
                    for _ in range(20):
                        f.call('ADProcess')
                    assert f.var('SensorStatus', index=3, width=1) == 1
                    for _ in range(2600):
                        f.call('SensorErrAction')
                    f.call('BoardErrAction')
                    observed = [f.p(617), f.var('IndoorSensorPartialStopFlag', width=1)]
                    assert observed == [1, int(mode != 2)], observed
                    f.var('ADC_Val', 2000, 6, 2)
                    for _ in range(20):
                        f.call('ADProcess')
                    f.call('SensorErrAction')
                    assert f.var('SensorStatus', index=3, width=1) == 0
                    assert f.p(617) == 1, 'Fault must stay latched until reset'
                    f.p(524, 1)
                    f.call('ErrorReset')
                    f.p(524, 0)
                    f.call('ErrorReset')
                    f.call('SensorErrAction')
                    f.call('BoardErrAction')
                    assert f.p(617) == 0
                    assert f.var('IndoorSensorPartialStopFlag', width=1) == 0
                    rows.append(dict(profile=profile, mode=mode,
                        electrical_type=electrical_type, invalid_raw=bad_raw,
                        fault_and_stop=observed, recovery_requires_reset=True))
    report = {'hardware_access': False,
        'scope': 'Actual linked ADC and error functions in ARM emulator; no physical board input or scheduling proof',
        'passed_cases': len(rows), 'cases': rows}
    (PACKAGE / 'raw_AI3_chain_ARM.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print('OFFLINE RAW AI3 CHAIN', len(rows), 'PASSED', flush=True)


if __name__ == '__main__':
    main()
