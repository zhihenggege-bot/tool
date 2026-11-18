"""Defrost raw HP input simulation on isolated-load V12.39 boards.

SWD changes the selected 316 DI polarity setting (316[2]/[4]) and legacy 330
HMI command inputs, derived from exact AXFs. Never writes outputs, lifecycle or
counters. Restore inputs/settings in finally; this does not qualify HP contacts.
"""
import struct
import json
import os
import time
import traceback
from remaining571_common_20261105 import Bench,now
from run_indoor_bench_20261105 import BOARDS,I,D,ConnectHelper
from test_defrost_lifecycle_arm import Firmware
from remaining529_manual_defrost_input_20261105 import manual_defrost


def main():
    previous=json.loads((D/os.environ.get('PSC_BENCH_PREVIOUS_BATCH_JOURNAL','continuation_batches.json')).read_text('utf8'))
    assert len(previous['batches'])==2 and all(v['exit_code']==0 for v in previous['batches']), 'Inspect previous failed batch before further writes'
    b=Bench('529_defrost_highpressure')
    symbols=Firmware(str(I/'PSC316_V12.39_BENCH_ONLY_3S.axf')).symbols
    with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as session:
        t=session.target
        param=symbols['Parameter'][0]
        old={reg:t.read16(param+reg*2) for reg in (2,4)}
        b.log['stimulus_boundary']='316[2]/[4] polarity simulation via SWD; no raw/latched fault, output, request, timer or lifecycle writes'
        b.log['outdoor_config_before']=old
        b.save()
        try:
            selected=((1,'T16-007'),) if os.environ.get('PSC_HP_ONLY_SECOND')=='1' else ((0,'T16-006'),(1,'T16-007'))
            for comp,cid in selected:
                b.setup(1)
                b.config({128:1,127:1,129:1,332:1,315:1,327:1,318:0,319:120,
                    125:0,126:0,160:250,161:250,412:1,347:100,348:1,349:0,346:0,365:1,372:350,12:500})
                b.ntc(0,220)
                b.ntc(2,0)
                b.reset_faults()
                b.start()
                b.wait(cid+' four compressors established',lambda s:all(v==3 for pair in s['outdoor_status'] for v in pair),150)
                b.wr(540,1)
                manual_defrost(b,True)
                b.wait(cid+' active defrost',lambda s:b.rd(1550)[0]==8,60)
                entry={'at':now(),'comp':comp,'samples':[],'reg':2+comp*2,'passed':False}
                b.log['cases'][cid]=entry
                reg=entry['reg']
                entry['before']={'Comp':list(t.read_memory_block8(symbols['Comp'][0],2)),
                    'raw':t.read8(symbols['X_00' if comp==0 else 'X_02'][0]),'status':b.rd(1550,2)}
                assert entry['before']['Comp']==[1,1] and entry['before']['raw']==0,entry['before']
                entry['injected_at']=now()
                entry['injected_monotonic']=time.monotonic()
                t.write16(param+reg*2,1-old[reg])
                t.flush()
                deadline=time.monotonic()+2.5
                try:
                    while True:
                        s={'at':now(),'elapsed_s':time.monotonic()-entry['injected_monotonic'],
                           'raw':t.read8(symbols['X_00' if comp==0 else 'X_02'][0]),
                           'Comp':list(t.read_memory_block8(symbols['Comp'][0],2)),
                           'phase':[t.read16(param+1420*2),t.read16(param+1421*2)],
                           'HPalarms':[t.read16(param+606*2),t.read16(param+607*2)]}
                        entry['samples'].append(s)
                        # SWD reads cross scan boundaries: do not interpret an
                        # old raw-input read plus a new stopped-output read as
                        # a simultaneous state. Require the next complete
                        # sample to show asserted input AND stopped circuit.
                        if s['raw']==1 and s['Comp'][comp]==0:
                            assert s['Comp'][1-comp]==1 and s['phase']==[8,8] and s['HPalarms']==[0,0],s
                            entry['trip']=s
                            break
                        assert time.monotonic()<deadline,('raw high pressure did not isolate circuit',s)
                        time.sleep(.03)
                finally:
                    t.write16(param+reg*2,old[reg])
                    t.flush()
                    entry['polarity_restored_at']=now()
                    b.save()
                entry['after_input_restore']=b.observe(cid+' no restart within defrost',2)
                assert t.read8(symbols['Comp'][0]+comp)==0
                assert b.rd(1550)[0]==8
                manual_defrost(b,False)
                entry['complete']=b.wait(cid+' reaches completed lifecycle',lambda s:b.rd(1550)[0]==0,180,True)
                entry['polarity_readback']=t.read16(param+reg*2)
                assert entry['polarity_readback']==old[reg]
                entry['passed']=True
                b.record(cid,'部分通过',f'V12.39化霜8已建立后，经316参数{reg}极性模拟原始高压：约{entry["trip"]["elapsed_s"]:.3f}s仅停压机{comp+1}，另一台保持；新高压报警未锁存；恢复输入后本次化霜不重启该压机，正常结束命令后生命周期清0。',
                    '316输入极性配置及330旧HMI命令输入RAM模拟；实际高压接点、压力信号和端子未测；原配置finally恢复；普通Modbus手动化霜入口被拦截，BENCH不能证明正式60s',entry)
                b.stop()
            b.log['passed']=True
        except BaseException:
            b.log['error']=traceback.format_exc()
            b.save()
            raise
        finally:
            for reg,value in old.items():t.write16(param+reg*2,value)
            t.flush()
            b.log['outdoor_config_restored']={str(r):t.read16(param+r*2)==v for r,v in old.items()}
            b.save()
            b.finish()
    print('DEFROST HP COMPLETE',b.path,flush=True)


if __name__=='__main__':main()
