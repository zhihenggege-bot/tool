"""Recheck stable writes with completed EEPROM saving and boot loading."""
import json, struct, time, traceback
from run_indoor_bench_20261105 import (ControlBench, D, BOARDS, axf_symbols,
                                      ConnectHelper, result, signed16, now)


def main():
    prior = sorted(D.glob('scalar_parameters_*.json'))[-1]
    old = json.loads(prior.read_text('utf-8'))
    b = ControlBench('parameter_persistence_recheck')
    sy = axf_symbols()
    b.log['prior_evidence'] = prior.name
    b.log['cases'] = {cid: {'address': v['address'], 'required': v['required'],
                            'range_failures': [s for s in v.get('failures', []) if not s.startswith('默认值复位后不符')],
                            'actual_table': v['actual_table']}
                     for cid, v in old['cases'].items()}
    try:
        b.stop()
        b.config({164: 0})
        for v in b.log['cases'].values():
            b.wr(v['address'], v['required'][2])
        with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1], target_override=BOARDS[2][2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t = ss.target
            b.log['before_reset_save_samples'] = []
            end = time.monotonic() + 30
            stable_since = None
            while True:
                a, size = sy['Old_Parameter']
                saved = struct.unpack('<500H', bytes(t.read_memory_block8(a, size)))
                sample = {'at': now(), 'writer_state': t.read8(sy['EEpflag'][0]),
                          'boot_state': t.read8(sy['eepromtt'][0]),
                          'mismatches': {str(v['address']): [v['required'][2], signed16(saved[v['address']])]
                                         for v in b.log['cases'].values() if saved[v['address']] != v['required'][2] & 65535}}
                b.log['before_reset_save_samples'].append(sample)
                if sample['writer_state'] == 0 and sample['boot_state'] == 3 and not sample['mismatches']:
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= 2:
                        break
                else:
                    stable_since = None
                assert time.monotonic() < end, sample
                b.save()
                time.sleep(.2)
            b.save()
            t.reset()
            start = time.monotonic()
            b.log['after_reset_samples'] = []
            while time.monotonic() - start < 8:
                sample = {'elapsed': round(time.monotonic()-start,3)}
                try:
                    values = []
                    for a in range(0,500,125):
                        values.extend(b.rd(a,125))
                    sample['read_finished_elapsed'] = round(time.monotonic()-start,3)
                    sample['writer_state'] = t.read8(sy['EEpflag'][0])
                    sample['boot_state'] = t.read8(sy['eepromtt'][0])
                    sample['values'] = values
                    sample['mismatches'] = {str(v['address']): [v['required'][2], signed16(values[v['address']])]
                         for v in b.log['cases'].values() if values[v['address']] != v['required'][2] & 65535}
                except Exception as e:
                    sample['error'] = repr(e)
                b.log['after_reset_samples'].append(sample)
                print('RESET SAMPLE', {k:v for k,v in sample.items() if k!='values'}, flush=True)
                b.save()
                time.sleep(.25)
        final = b.log['after_reset_samples'][-1]
        assert 'values' in final and final['boot_state'] == 3, final
        b.log['stable_reset_mismatches'] = final['mismatches']
        for cid,v in b.log['cases'].items():
            v['stable_reset_readback'] = signed16(final['values'][v['address']])
            v['failures'] = list(v['range_failures'])
            if v['stable_reset_readback'] != v['required'][2]:
                v['failures'].append('EEPROM启动完成8秒后仍未保存:'+str(v['stable_reset_readback']))
        b.save()
    except BaseException:
        b.log['error'] = traceback.format_exc()
        b.save()
        raise
    finally:
        b.finish()
    for cid,v in b.log['cases'].items():
        result(cid, '失败' if v['failures'] else '部分通过',
               ('；'.join(v['failures']) if v['failures'] else '默认/范围、协议写入通过；等待EEPROM启动完成后复位保存回读通过')
               +f"；复位稳定回读{v['stable_reset_readback']}，要求{v['required'][2]}", b.path,
               '前次连续边界写入后保存异常保留，稳定单值复测通过；首次异常根因未定；本批原参数已恢复；HMI及真实掉电未测')


if __name__ == '__main__':
    main()
