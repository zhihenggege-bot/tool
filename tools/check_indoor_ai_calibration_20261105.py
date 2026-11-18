"""BENCH software calibration isolation check; not physical signal calibration."""
import time, traceback
from run_indoor_bench_20261105 import ControlBench, result, signed16, now


def main():
    b = ControlBench('ai_calibration_isolation')
    ok = False
    actual = ''
    try:
        b.stop()
        b.config({164: 0})
        displays = [902, 501, 903, 1125, 519]

        def readings():
            return [signed16(b.rd(a)[0]) for a in displays]

        # Keep actual ADC input and filters. Temporarily use a nonzero span so
        # an offset can be observed without an equal-endpoint output clamp.
        for ch in range(5):
            a = 1229 + 12 * ch
            b.config({a: 1, a + 2: 0, a + 3: 1000,
                      a + 4: 100, a + 5: 1100,
                      a + 6: 100, a + 7: 1100, a + 8: 0})
        time.sleep(2)
        b.log['baseline_ai'] = readings()
        b.log['baseline_raw'] = b.rd(904,5)
        assert all(0 <= raw <= 10000 for raw in b.log['baseline_raw']), 'ADC outside configured signal span'
        b.log['stimulus'] = '信号范围0~1000，工程范围100~1100，偏移0/±10；保留真实ADC输入；非物理信号校准'
        b.log['checks'] = []
        for ch in range(5):
            a = 1237 + 12 * ch
            before_ntc = signed16(b.rd(511)[0])
            baseline = readings()
            change = -10 if baseline[ch] > 1090 else 10
            b.wr(a, change)
            expected = baseline.copy()
            expected[ch] += change
            end = time.monotonic() + 8
            while any(abs(x-y)>3 for x,y in zip(readings(),expected)):
                assert time.monotonic() < end, (ch, 'offset/crosstalk', expected, readings())
                time.sleep(.2)
            after_ntc = signed16(b.rd(511)[0])
            assert abs(after_ntc - before_ntc) <= 3, ('NTC changed during AI offset', ch, before_ntc, after_ntc)
            b.log['checks'].append({'at': now(), 'channel': ch, 'new_offset_address': a,
                                    'baseline': baseline, 'requested_offset': change,
                                    'ai_values': readings(), 'raw_values': b.rd(904,5),
                                    'ntc_before_after': [before_ntc, after_ntc]})
            b.wr(a, 0)
            end = time.monotonic() + 8
            while any(abs(x-y)>3 for x,y in zip(readings(),baseline)):
                assert time.monotonic() < end, ('offset restoration', ch, readings())
                time.sleep(.2)
            b.save()
        offset = signed16(b.rd(495)[0])
        stimulus = offset + 10 if offset <= 90 else offset - 10
        before = signed16(b.rd(511)[0])
        ai_before_ntc = readings()
        b.wr(495, stimulus)
        end = time.monotonic() + 8
        while abs((signed16(b.rd(511)[0]) - before) - (stimulus - offset)) > 3:
            assert time.monotonic() < end, ('NTC offset not observed', before, b.rd(511))
            time.sleep(.2)
        assert all(abs(x-y)<=3 for x,y in zip(readings(),ai_before_ntc)), ('NTC/AI crosstalk', ai_before_ntc,readings())
        b.log['ntc_check'] = {'address': 495, 'offset_before_after': [offset, stimulus],
                              'temperature_before_after': [before, signed16(b.rd(511)[0])],
                              'ai_after': readings()}
        b.wr(495, offset)
        b.save()
        ok = True
        actual = 'AI0~AI4新偏移1237/1249/1261/1273/1285逐路±10，仅对应软件读数变化；NTC0[495]独立改变温度且AI4不变；前次等量程被夹限的测试夹具错误已纠正'
    except BaseException:
        actual = traceback.format_exc()
        b.log['error'] = actual
        b.save()
        raise
    finally:
        try:
            b.finish()
        finally:
            result('T01-004', '部分通过' if ok else '失败', actual, b.path,
                   '已停止并恢复原配置，恢复状态见证据；物理0~10V/4~20mA三点、真实掉电与EEPROM初始迁移未测',
                   '串口正常校准/量程写入；无RAM写入、无旧AI校准地址写入')


if __name__ == '__main__':
    main()
