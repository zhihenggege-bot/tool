"""Keep the unit running while verifying heat-fault latch/reset recovery.

Normal parameter/DI polarity stimulation; no output or protection RAM writes.
"""
import time
import traceback
from run_indoor_bench_20261105 import ControlBench, now, signed16


def main():
    b = ControlBench('heater_humidity_recovery')
    polarities = {a: b.rd(a)[0] for a in (390, 391)}

    def reset():
        b.wr(524, 1)
        time.sleep(.3)
        b.wr(524, 0)

    def hold(label, seconds, predicate):
        start = time.monotonic()
        samples = []
        while time.monotonic() - start < seconds:
            s = b.snapshot(label)
            s['heating_fault'] = b.rd(924)[0]
            samples.append(s)
            assert not any(s['faults']), (label, 'other fault', s)
            assert predicate(s), (label, s)
            time.sleep(.25)
        return samples

    def fans(s):
        return s['state'][9] == 2 and s['do'][3] == 1 and s['do'][6] == 1 and s['do'][8] == 1

    def humid_off(s):
        return s['ao'][2] == 0 and s['do'][11] == 0

    try:
        b.baseline(0)
        b.config({329: 2, 330: 2, 331: 1, 134: 50, 131: 50,
                  125: 1, 126: 1, 127: 1, 128: 2, 129: 1, 332: 1, 333: 0,
                  334: 1, 248: 1, 168: 1, 169: 1, 160: 250, 161: 250,
                  347: 100, 348: 1, 349: 0, 412: 1,
                  1241: 1, 1245: 299, 1246: 301, 1247: 299, 1248: 301, 1249: 0})
        target_offset = signed16(b.rd(495)[0]) + 220 - signed16(b.rd(511)[0])
        assert -100 <= target_offset <= 100
        b.wr(495, target_offset)
        time.sleep(4)
        reset()
        b.wr(398, 1)
        for polarity, humid in ((390, 1), (390, 2), (391, 1), (391, 2)):
            cid = f'R-X{6 if polarity == 390 else 7:02d}-' + ('AO' if humid == 1 else 'DO')
            entry = {'started': now(), 'polarity_address': polarity,
                     'humidifier_type': humid, 'physical_contacts_measured': False}
            b.log['cases'][cid] = entry
            print('RECOVERY START', cid, flush=True)
            b.wr(334, humid)
            entry['before'] = b.wait(cid + ' established',
                lambda s: fans(s) and s['ao'][0] > 0 and
                    (s['ao'][2] > 0 if humid == 1 else s['do'][11] == 1), 25)
            b.wr(polarity, 1 - polarities[polarity])
            b.wait(cid + ' latched', lambda s: b.rd(924)[0] == 1 and humid_off(s), 10, True)
            reset()
            entry['reset_while_input_active'] = hold(cid + ' active input reset', 2,
                lambda s: fans(s) and humid_off(s) and s['heating_fault'] == 1 and
                    (s['ao'][0] == 0 if polarity == 390 else s['ao'][0] > 0))
            b.wr(polarity, polarities[polarity])
            # The input release must pass the existing DI filter before reset.
            entry['input_removed_without_reset'] = hold(cid + ' release no reset', 5,
                lambda s: fans(s) and humid_off(s) and s['heating_fault'] == 1)
            reset()
            entry['after_reset'] = b.wait(cid + ' recovered',
                lambda s: fans(s) and b.rd(924)[0] == 0 and s['ao'][0] > 0 and
                    (s['ao'][2] > 0 if humid == 1 else s['do'][11] == 1), 25)
            entry['passed'] = True
            entry['finished'] = now()
            b.save()
            print('RECOVERY PASSED', cid, flush=True)
        b.log['passed'] = True
    except BaseException:
        b.log['error'] = traceback.format_exc()
        b.save()
        raise
    finally:
        try:
            b.wr(398, 0)
            for a, v in polarities.items():
                b.wr(a, v)
            time.sleep(4)
            reset()
        finally:
            b.finish()
    print('RECOVERY COMPLETE', b.path, flush=True)


if __name__ == '__main__':
    main()
