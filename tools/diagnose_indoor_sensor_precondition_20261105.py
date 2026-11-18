"""Read-only sensor evidence using symbols from the flashed BENCH AXF."""
import struct
import time
from run_indoor_bench_20261105 import BOARDS, ConnectHelper, D, axf_symbols, client, dump, now


def main():
    c = client()
    sy = axf_symbols()
    path = D / ('sensor_precondition_' + time.strftime('%H%M%S') + '.json')
    report = {'started': now(), 'read_only': True, 'samples': [],
              'indoor_fault_map': {'618': 'ROOMTempErr / SensorErr[5]',
                                   '619': 'ROOMHumidtyErr / SensorErr[1]'}}
    try:
        with ConnectHelper.session_with_chosen_probe(
                unique_id=BOARDS[2][1], target_override=BOARDS[2][2],
                options={'connect_mode': 'attach', 'resume_on_disconnect': True,
                         'frequency': 1000000}) as ss:
            start = time.monotonic()
            while time.monotonic() - start < 12:
                sample = {'at': now(), 'elapsed': time.monotonic() - start,
                          'raw_ai': c.read_holding_registers(1, 904, 5),
                          'room_humidity': c.read_holding_registers(1, 501, 1),
                          'room_temperature': c.read_holding_registers(1, 511, 1),
                          'ntc_raw': c.read_holding_registers(1, 1374, 12),
                          'faults': c.read_holding_registers(1, 594, 33),
                          'ai1_config': c.read_holding_registers(1, 1241, 12)}
                for name in ('SensorStatus', 'SensorErr'):
                    address, size = sy[name]
                    sample[name] = ss.target.read_memory_block8(address, size)
                for name in ('ADC_Val', 'AD_Val', 'AI'):
                    address, size = sy[name]
                    sample[name] = list(struct.unpack('<' + 'H' * (size // 2),
                        bytes(ss.target.read_memory_block8(address, size))))
                report['samples'].append(sample)
                print(sample['at'], 'AI', sample['raw_ai'], 'ADC', sample['ADC_Val'],
                      'status', sample['SensorStatus'][:5], flush=True)
                time.sleep(.5)
        report['finished'] = now()
    finally:
        dump(path, report)
        c.close()
        print(path, flush=True)


if __name__ == '__main__':
    main()
