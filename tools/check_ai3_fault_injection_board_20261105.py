"""User-authorized AI3 fault-latch injection; board scheduler drives all effects.

Only SensorErr[3] is written through SWD. No requests, counts, outputs, ADC values,
or other faults are written. This skips electrical diagnosis and its delay.
"""
import argparse
import time
import traceback
from remaining571_common_20261105 import Bench, now
from run_indoor_bench_20261105 import BOARDS, EXPECTED, ConnectHelper, axf_symbols


def main(outdoors_only=False, from_index=0):
    b = Bench('ai3_latch_injection')
    sy = axf_symbols()
    b.log['stimulus_boundary'] = 'SWD writes SensorErr[3]=1 only; bypasses physical ADC and diagnostic delay'
    b.log['hardware_access'] = True
    b.log['ram_write_allowlist'] = {'SensorErr[3]': sy['SensorErr'][0] + 3}
    assert b.rd(2622, 18) == EXPECTED
    assert b.rd(1298, 2) == [3, 15107]
    session = ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],
        target_override=BOARDS[2][2], options={'connect_mode': 'attach',
        'resume_on_disconnect': True, 'frequency': 1000000})
    with session as ss:
        target = ss.target

        def sample(label):
            s = b.sample(label)
            s['SensorErr3'] = target.read8(sy['SensorErr'][0] + 3)
            s['SensorStatus3'] = target.read8(sy['SensorStatus'][0] + 3)
            s['partial_stop'] = target.read8(sy['IndoorSensorPartialStopFlag'][0])
            return s

        def wait(label, condition, seconds=30):
            end = time.monotonic() + seconds
            while True:
                s = sample(label)
                if condition(s):
                    b.save()
                    return s
                assert time.monotonic() < end, (label, s)
                time.sleep(.2)

        def inject(entry):
            assert target.read8(sy['SensorErr'][0] + 3) == 0
            entry['injection_at'] = now()
            entry['injection_monotonic'] = time.monotonic()
            entry['write'] = {'symbol': 'SensorErr[3]', 'address': sy['SensorErr'][0] + 3, 'width': 1, 'before': 0, 'value': 1}
            b.save()
            target.write8(sy['SensorErr'][0] + 3, 1)
            target.flush()

        def fans_valves(s):
            return s['state'][9] == 2 and all(s['do'][i] == 1 for i in (3, 6, 8, 4, 7, 9, 12))

        def thermal_off(s):
            return all(s['ao'][i] == 0 for i in (0, 1, 2, 8, 9)) and all(s['do'][i] == 0 for i in (0, 1, 2, 11, 13, 14))

        def hold(label, condition, seconds=4):
            rows = []
            end = time.monotonic() + seconds
            while True:
                s = sample(label)
                rows.append(s)
                assert condition(s), (label, s)
                if time.monotonic() >= end:
                    b.save()
                    return rows
                time.sleep(.25)

        try:
            cases = [] if outdoors_only else [
                (0, 1, 1, 'T03-027'), (1, 1, 2, 'T03-029'), (2, 1, 0, 'T03-031'),
                (0, 0, 2, 'T03-033'), (1, 0, 1, 'T03-035'), (2, 0, 0, 'T03-037')]
            for mode, basis, humid, cid in cases[from_index:]:
                print('START', cid, 'mode', mode, 'basis', basis, 'humid', humid, flush=True)
                entry = {'started': now(), 'mode': mode, 'basis': basis, 'humidifier': humid}
                b.log['cases'][cid] = entry
                b.setup(mode, thermal=mode != 2)
                b.config({329: 3, 133: basis, 339: 60, 340: 60, 341: 30, 342: 90,
                    343: 720, 344: 100, 345: 100, 290: 5, 291: 10,
                    335: 1, 336: 1, 337: 1, 338: 1,
                    168: int(mode != 2), 169: int(mode != 2), 334: humid,
                    333: int(mode == 1), 374: 0, 357: 100, 358: 0})
                b.ai(3, 100, 20)
                if mode == 1:
                    b.ntc(2, 20)
                b.reset_faults()
                b.start()
                def established(s):
                    return fans_valves(s) and (mode == 2 or (
                        s['ao'][0] > 0 and (mode != 1 or s['ao'][1] > 0) and
                        (s['ao'][2] > 0 if humid == 1 else s['do'][11] == 1)))
                entry['before'] = wait(cid + ' loads established', established)
                inject(entry)
                entry['fault'] = wait(cid + ' fault acted', lambda s:
                    s['faults'][23] == 1 and s['partial_stop'] == int(mode != 2) and
                    fans_valves(s) and s['ao'][7] == 600 and thermal_off(s), 10)
                entry['reaction_observed_s'] = round(time.monotonic() - entry['injection_monotonic'], 3)
                entry['latched_hold'] = hold(cid + ' no reset', lambda s:
                    s['SensorErr3'] == 1 and s['SensorStatus3'] == 0 and
                    s['faults'][23] == 1 and fans_valves(s) and thermal_off(s) and s['ao'][7] == 600)
                if mode == 2:
                    b.stop()
                    assert b.rd(617)[0] == 1
                    # This phase deliberately restarts with an expected alarm;
                    # the generic healthy-start helper rejects all alarm bits.
                    b.wr(398, 1)
                    entry['vent_fault_restart'] = wait(cid + ' vent restart with fault',
                        lambda s: fans_valves(s) and s['faults'][23] == 1 and s['ao'][7] == 600)
                b.reset_faults()
                entry['after_reset'] = wait(cid + ' recovered', lambda s:
                    s['faults'][23] == 0 and s['SensorErr3'] == 0 and s['partial_stop'] == 0 and established(s))
                entry['passed'] = True
                entry['finished'] = now()
                b.record(cid, '部分通过',
                    f'V10.51板上AI3锁存输入模拟：模式{mode}/风机依据{basis}/加湿{humid}；故障后热/预热/加湿等软件输出归0、风机风阀保持、送风AO回退600；4秒不复位仍锁存；524复位恢复。'+('通风带故障正常停止再启动已测。' if mode == 2 else ''),
                    '仅SensorErr[3]输入注入；未物理开路/短路，未覆盖ADC检测延时、端子及正式档；另见外机实际反馈专项。', entry)
                b.stop()

            if outdoors_only:
                for mode in (0, 1):
                    cid = 'AI3-outdoor-' + str(mode)
                    entry = {'started': now(), 'mode': mode}
                    b.log['cases'][cid] = entry
                    b.setup(mode)
                    b.config({329: 3, 133: 1, 339: 60, 340: 60, 341: 30, 342: 90,
                        345: 100, 335: 1, 336: 1, 337: 1, 338: 1,
                        128: 1 if mode == 1 else 0, 125: 0, 127: 0,
                        160: 250, 161: 250, 412: 1, 416: 100, 417: 1, 418: 0,
                        422: 5, 426: 100, 427: 1, 428: 0, 42: 3, 43: 3})
                    b.ai(3, 100, 20)
                    b.ntc(0, 280 if mode == 0 else 220)
                    b.ntc(2, 160 if mode == 0 else 60)
                    b.reset_faults()
                    b.start()
                    entry['before'] = wait(cid + ' actual compressors established',
                        lambda s: fans_valves(s) and s['count_119'] >= 1, 130)
                    inject(entry)
                    entry['after'] = wait(cid + ' actual compressors stopped', lambda s:
                        s['faults'][23] == 1 and s['partial_stop'] == 1 and
                        s['count_119'] == 0 and fans_valves(s) and thermal_off(s), 45)
                    entry['observed_stop_s'] = round(time.monotonic() - entry['injection_monotonic'], 3)
                    entry['hold'] = hold(cid + ' compressor stays stopped', lambda s:
                        s['count_119'] == 0 and s['faults'][23] == 1 and fans_valves(s) and thermal_off(s))
                    b.reset_faults()
                    entry['recovered'] = wait(cid + ' compressor restart after reset', lambda s:
                        s['faults'][23] == 0 and s['partial_stop'] == 0 and s['count_119'] >= 1, 130)
                    entry['passed'] = True
                    entry['finished'] = now()
                    b.save()
                    print('OUTDOOR PASSED', cid, 'stop_s', entry['observed_stop_s'], flush=True)
                    b.stop()
            b.log['passed'] = True
        except BaseException:
            b.log['error'] = traceback.format_exc()
            b.save()
            raise
        finally:
            try:
                b.reset_faults()
                b.log['sensor_latch_after_reset'] = target.read8(sy['SensorErr'][0] + 3)
                assert b.log['sensor_latch_after_reset'] == 0
            finally:
                b.finish()
    print('DONE', b.path, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--outdoors-only', action='store_true')
    p.add_argument('--from-index', type=int, default=0)
    args = p.parse_args()
    main(args.outdoors_only, args.from_index)
