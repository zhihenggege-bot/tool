"""Demonstrate a lost valid update inside actual EEPROM writer ARM code."""
import json
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_LR,UC_ARM_REG_PC


def exercise(path,addr,writer='WriteParamaterEEprom',state='EEpflag',change_after_low=True):
    f=Firmware(str(path.relative_to(ROOT)))
    f.uc.mem_map(0x22000000,0x100000)
    f.call('ParameterInit')
    for i in range(500):
        value=f.var('Parameter_def',index=i,width=2)
        f.p(i,value);f.var('Old_Parameter',value,i,2)
    if 'SyncRS485AddressParamsFromPublic' in f.symbols:
        f.call('SyncRS485AddressParamsFromPublic')
        for i in range(500):f.var('Old_Parameter',f.p(i),i,2)
    # A known saved setting, followed by two legal different requests.
    old,first,last=(50,100,0) if addr==134 else (100,150,50)
    f.p(addr,old);f.var('Old_Parameter',old,addr,2)
    mem={};events=[]
    def stub(uc,pc,size,_):
        r0=uc.reg_read(UC_ARM_REG_R0);r1=uc.reg_read(UC_ARM_REG_R1)
        if pc==(f.symbols['CI2C_WriteByte'][0]&~1):
            mem[r1]=r0&255;events.append({'write':[r1,r0&255]})
        elif pc==(f.symbols['CI2C_ReadByte'][0]&~1):
            a=uc.reg_read(UC_ARM_REG_R2)
            uc.mem_write(r0,bytes(mem.get(a+i,0) for i in range(r1)))
            events.append({'read':[a,r1]})
        else:return
        uc.reg_write(UC_ARM_REG_R0,1)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    f.uc.hook_add(UC_HOOK_CODE,stub)
    f.var('Systick_1ms',30000)
    f.p(addr,first)
    # The original writer uses one state per call: select/high/low/verify.
    for step in range(4):
        if step==(3 if change_after_low else 2):f.p(addr,last)
        f.var('Systick_1ms',30000+step*10)
        f.call(writer)
        events.append({'step':step,'state':f.var(state),'runtime':f.p(addr),
                       'saved':f.var('Old_Parameter',index=addr,width=2)})
    return {'image':str(path.relative_to(ROOT)),'parameter':addr,'saved_before':old,
            'first_request':first,'latest_request':last,'actual_after_verify':f.p(addr),
            'lost_latest_request':f.p(addr)!=last,'events':events}


def main():
    root=ROOT/'.codex-tmp/fan_enable_v1048_v1238_20261104/BENCH_ONLY_3S'
    results=[exercise(root/'PSC330_V10.48_BENCH_ONLY_3S.axf',134),
             exercise(root/'PSC316_V12.38_BENCH_ONLY_3S.axf',182)]
    dest=ROOT/'测试证据/内机实测_20261105/参数连续写入竞态_ARM定位.json'
    dest.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n','utf-8')
    for item in results:print(item['image'],item['lost_latest_request'],item['actual_after_verify'],flush=True)
    assert all(v['lost_latest_request'] for v in results),'Expected old writer race not reproduced'


if __name__=='__main__':main()
