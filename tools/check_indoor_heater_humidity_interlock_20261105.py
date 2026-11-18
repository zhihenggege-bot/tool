"""Normal DI polarity simulation, with actual control demands established first.

This exercises board filtering/latching, not physical contact injection.
"""
import time, traceback
from run_indoor_bench_20261105 import ControlBench, result, signed16, now


def main():
    b = ControlBench('heater_humidity_interlock')
    original_polarity = b.rd(390)[0]
    original_preheat_polarity = b.rd(391)[0]

    def clear():
        b.wr(398, 0)
        b.wr(390, original_polarity)
        b.wr(391, original_preheat_polarity)
        time.sleep(3.5)
        b.wr(524, 1)
        time.sleep(.3)
        b.wr(524, 0)
        b.wait('heater fault reset', lambda s:b.rd(924)[0] == 0, 10, True)
        b.stop()

    try:
        for mode, humid, cid, polarity in [(0,1,'T03-001',390),(0,2,'T03-002',390),
            (0,1,'T03-003',391),(0,2,'T03-004',391),(1,1,'T03-005',390),
            (1,2,'T03-006',390),(1,1,'T03-007',391),(1,2,'T03-008',391)]:
            fault_name='X06' if polarity==390 else 'X07'
            original_fault_polarity=original_polarity if polarity==390 else original_preheat_polarity
            entry = {'started':now(), 'mode':mode, 'humidifier_type':humid,
                     'stimulus':f'{fault_name}正常极性参数{polarity}翻转；经过实际DI过滤和锁存；非物理接点'}
            b.log['cases'][cid] = entry
            print('CASE START', cid, flush=True)
            try:
                b.baseline(mode)
                b.config({329:2, 330:2, 331:1, 134:50, 131:50,
                          125:1, 126:1, 127:1, 128:2, 129:1, 332:1, 333:0,
                          334:humid, 248:1, 168:1, 169:1,
                          160:250, 161:250, 347:100, 348:1, 349:0, 412:1})
                base = 1241
                # A narrow nonzero engineering span avoids a constant-map
                # clamp. This does not bypass the physical ADC diagnostics.
                b.config({base:1,base+4:299,base+5:301,base+6:299,base+7:301,base+8:0})
                current = signed16(b.rd(511)[0])
                offset = signed16(b.rd(495)[0]) + 220-current
                assert -100<=offset<=100, ('room target22C unreachable within legal calibration',current,offset)
                b.wr(495, offset)
                b.wait('room22C', lambda s:abs(signed16(b.rd(511)[0])-220)<=3, 10, True)
                # Enabling an input while its scale words are being configured
                # can leave a startup diagnostic until conversion settles/reset.
                time.sleep(3.5)
                b.wr(524,1);time.sleep(.3);b.wr(524,0)
                stable_start=time.monotonic()
                while time.monotonic()-stable_start<8:
                    s=b.snapshot('humidity input precondition')
                    s['room_temperature']=b.rd(511)[0]
                    s['room_humidity']=b.rd(501)[0]
                    s['ntc0_raw']=b.rd(1374)[0]
                    assert not any(s['faults']), ('sensor precondition',s)
                    time.sleep(.3)
                assert b.rd(1356)==[0], ('X06 already active',b.rd(1356))
                b.wr(398,1)
                before = b.wait(cid+' heat+humid established',
                    lambda s:s['state'][9]==2 and s['ao'][0]>0 and
                      (s['ao'][2]>0 if humid==1 else s['do'][11]==1), 30)
                entry['before'] = before
                injected_at = time.monotonic()
                b.wr(polarity,1-original_fault_polarity)
                latched = b.wait(cid+' heat fault latched',lambda s:b.rd(924)==[1],10,True)
                entry['latched_elapsed_s'] = round(time.monotonic()-injected_at,3)
                entry['after_samples'] = []
                end = time.monotonic()+5
                while time.monotonic()<end:
                    s = b.snapshot(cid+' after fault')
                    entry['after_samples'].append(s)
                    time.sleep(.3)
                checks = entry['after_samples']
                entry['affected_heat_off'] = all(s['ao'][0 if polarity==390 else 1]==0 for s in checks)
                entry['affected_heat_was_running'] = before['ao'][0 if polarity==390 else 1]>0
                entry['humidifier_off'] = all(s['ao'][2]==0 and s['do'][11]==0 for s in checks)
                entry['fans_continue'] = all(s['state'][9]==2 and s['do'][3]==1 and s['do'][6]==1 for s in checks)
                entry['software_passed'] = entry['affected_heat_off'] and entry['humidifier_off'] and entry['fans_continue']
                entry['finished'] = now()
                b.save()
                clear()
                result(cid,'部分通过' if entry['software_passed'] else '失败',
                    f"{fault_name}故障锁存在{entry['latched_elapsed_s']}s出现；对应热AO关闭={entry['affected_heat_off']}（故障前该热路运行={entry['affected_heat_was_running']}），加湿全关={entry['humidifier_off']}，风机保持={entry['fans_continue']}；连续5s逐样本检查", b.path,
                    '本例正常停机、恢复极性并复位清故障；物理接点/端子及正式版未测；本批最终恢复见证据',entry['stimulus'])
            except BaseException:
                entry['error'] = traceback.format_exc()
                b.save()
                blocked = any(x in entry['error'] for x in ('unreachable within legal calibration', 'sensor precondition'))
                result(cid,'环境受限' if blocked else '失败',
                       entry['error'].splitlines()[-1],b.path,'实际刺激及恢复详见原始记录；未满足前置时不判通过')
                raise
    finally:
        try:
            clear()
        finally:
            b.finish()


if __name__ == '__main__':
    main()
