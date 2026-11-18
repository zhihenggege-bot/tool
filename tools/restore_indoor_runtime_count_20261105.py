"""Explicitly restore the stale, writable [119] cache after journaling it."""
import time
from run_indoor_bench_20261105 import D, R, BOARDS, ConnectHelper, axf_symbols, client, dump, loads_off, now, snap
import json


def main():
    c = client()
    p = D / ('runtime_count_restore_' + time.strftime('%H%M%S') + '.json')
    data = {'started': now(), 'scope': 'normal Modbus restore of writable cached runtime count [119]; no firmware fix'}
    try:
        data['before'] = snap(c)
        data['before_119'] = c.read_holding_registers(1, 119, 1)[0]
        wanted = json.loads((D/'preflight.json').read_text('utf-8'))['config']['119']
        data['preflight_119'] = wanted
        assert data['before']['state'][9] == 0 and loads_off(data['before'])
        assert data['before']['outdoor_status'] == [[0, 0], [0, 0]]
        assert data['before_119'] == 1 and wanted == 0
        dump(p, data)
        c.write_single_register(1, 119, wanted)
        sy = axf_symbols()
        with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1], target_override=BOARDS[2][2],
                options={'connect_mode': 'attach', 'resume_on_disconnect': True, 'frequency': 1000000}) as ss:
            end = time.monotonic()+15
            while ss.target.read16(sy['Old_Parameter'][0] + 238) != wanted:
                assert time.monotonic()<end, 'runtime count did not persist'
                time.sleep(.1)
        data['after_119'] = c.read_holding_registers(1, 119, 1)[0]
        assert data['after_119'] == wanted
        data['after'] = snap(c)
        data['restored'] = True
        data['finished'] = now()
    finally:
        dump(p, data)
        c.close()
    print('CACHE RESTORED; STOPPED-STATE REFRESH ISSUE REMAINS', p, flush=True)


if __name__ == '__main__':
    main()
