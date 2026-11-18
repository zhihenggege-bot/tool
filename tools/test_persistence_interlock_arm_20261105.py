"""Execute the actual new ARM writers, journal and humidity interlock, both profiles."""
import json,hashlib
from test_defrost_lifecycle_arm import Firmware,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_LR,UC_ARM_REG_PC
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB

PACKAGE=ROOT/'.codex-tmp/persistence_interlock_v1049_v1239_20261105'
checks=[]
def check(ok,label):
    checks.append({'label':label,'passed':bool(ok)})
    assert ok,label

def setup(model,profile):
    version='10.49' if model==330 else '12.39'
    path=PACKAGE/profile/f'PSC{model}_V{version}_{profile}.axf'
    f=Firmware(str(path.relative_to(ROOT)));f.uc.mem_map(0x22000000,0x100000)
    f.call('ParameterInit')
    for i in range(500):f.p(i,f.var('Parameter_def',index=i,width=2))
    if model==316:f.call('SyncRS485AddressParamsFromPublic')
    for i in range(500):f.var('Old_Parameter',f.p(i),i,2)
    f.var('Systick_1ms',30000)
    f.mem={};f.writes=[];f.failure=False
    def stub(uc,pc,size,_):
        a=uc.reg_read(UC_ARM_REG_R0);b=uc.reg_read(UC_ARM_REG_R1)
        if pc==(f.symbols['CI2C_WriteByte'][0]&~1):
            if not f.failure:f.mem[b]=a&255
            f.writes.append([b,a&255])
        elif pc==(f.symbols['CI2C_ReadByte'][0]&~1):
            c=uc.reg_read(UC_ARM_REG_R2)
            uc.mem_write(a,bytes(f.mem.get(c+i,0) for i in range(b)))
        else:return
        uc.reg_write(UC_ARM_REG_R0,int(not f.failure));uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    f.uc.hook_add(UC_HOOK_CODE,stub)
    return f

def step(f,fn='WriteParamaterEEprom',dt=10):
    f.var('Systick_1ms',f.var('Systick_1ms')+dt);f.call(fn)

def run():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for model in (330,316):
            label=f'{model}/{profile}'
            for phase in (2,3):
                for failed in (False,True):
                    f=setup(model,profile);addr=134 if model==330 else 182
                    old,first,last=(50,100,0) if model==330 else (100,150,50)
                    f.p(addr,old);f.var('Old_Parameter',old,addr,2);f.p(addr,first)
                    f.failure=failed
                    for n in range(4):
                        if n==phase:f.p(addr,last)
                        step(f)
                    check(f.p(addr)==last,f'{label} phase{phase} failure{failed}: latest legal request retained')
                    if not failed:
                        check(f.var('Old_Parameter',index=addr,width=2)==first,f'{label} snapshot acknowledged')
                        check(f.mem[16+2*addr]*256+f.mem[17+2*addr]==first,f'{label} coherent snapshot bytes')
                    f.failure=False
                    for _ in range(8):step(f)
                    check(f.var('Old_Parameter',index=addr,width=2)==last and
                          f.mem[16+2*addr]*256+f.mem[17+2*addr]==last,f'{label} latest request eventually persisted')
            # Cross a byte boundary: a mixed word would be 0x01ff or 0x0000.
            f=setup(model,profile);addr=134 if model==330 else 182
            f.var('Parameter_max',1000,addr,2);f.p(addr,256)
            step(f);step(f);f.p(addr,255);step(f);step(f)
            check(f.var('Old_Parameter',index=addr,width=2)==256 and f.p(addr)==255,f'{label} byte boundary snapshot')
            for _ in range(4):step(f)
            check(f.var('Old_Parameter',index=addr,width=2)==255,f'{label} byte boundary converges')
            f=setup(model,profile);addr=134 if model==330 else 182
            f.p(addr,70);step(f);step(f);writes=len(f.writes);step(f,dt=7)
            check(len(f.writes)==writes,f'{label} EEPROM minimum write gap retained')
            # Genuine failure without a replacement command retains legacy rollback/error policy.
            f=setup(model,profile);old=f.p(addr);f.p(addr,70);f.failure=True
            for _ in range(4):step(f)
            check(f.p(addr)==old and f.var('CPURomWriteError')==addr,f'{label} actual storage failure reported')
        f=setup(330,profile)
        target=f.symbols['WriteParamaterEEprom'][0]&~1;a,n=f.symbols['sysRunfile']
        instructions=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(bytes(f.uc.mem_read(a&~1,n)),a&~1))
        check(any(i.mnemonic=='bl' and int(i.op_str.lstrip('#'),16)==target for i in instructions),
              f'{profile} binary sysRunfile calls owned replacement writer')
        check('IndoorParameterSaveState' in f.symbols,f'{profile} replacement writer diagnostic state linked')
        check((f.var('Parameter_min',index=340,width=2),f.var('Parameter_max',index=345,width=2))==(0,9999),
              f'{profile} user requested parameter ranges retained')
        check((f.var('Parameter_def',index=340,width=2),f.var('Parameter_def',index=345,width=2))==(100,5),
              f'{profile} 10V/5Pa defaults retained')
        for mode in (0,1):
            for humid in (1,2):
                for fault in ('HeatingFaultDisp','X06_En','X07_En'):
                    g=setup(330,profile)
                    for a,v in {709:2,236:mode,125:1,126:1,334:humid,248:1,168:1,169:1}.items():g.p(a,v)
                    # Fault latches and raw filtered inputs all inhibit the main control writer.
                    g.call('HumidtCtrl')
                    check((g.var('DA',index=2,width=2)>0 if humid==1 else g.var('output',index=11,width=1)==1),
                          f'{profile} mode{mode} humid{humid}: demand established before {fault}')
                    if fault=='HeatingFaultDisp':g.p(924,1)
                    else:g.var(fault,1)
                    g.call('HumidtCtrl')
                    check(g.var('DA',index=2,width=2)==0 and g.var('output',index=11,width=1)==0,
                          f'{profile} mode{mode} humid{humid}: {fault} clears both humidity outputs')
        # Journal must not claim new live values were saved in an older record.
        f=setup(330,profile);f.var('IndoorAiCfgLoaded',1)
        for i in range(60):
            f.p(1229+i,0);f.var('IndoorAiCfgShadow',0,i,2);f.var('IndoorAiLastSeen',0,i,2)
        f.p(1237,10);step(f,'IndoorAiCfgTask');step(f,'IndoorAiCfgTask',5000)
        check(f.var('IndoorAiStState')==1,f'{profile} AI journal snapshot started')
        f.p(1237,20)
        for _ in range(128):step(f,'IndoorAiCfgTask')
        step(f,'IndoorAiCfgTask')
        check(f.p(1237)==20 and f.var('IndoorAiCfgShadow',index=8,width=2)==10 and f.var('IndoorAiCfgDirty')==1,
              f'{profile} AI mid-save update stays dirty; acknowledge written snapshot only')
        step(f,'IndoorAiCfgTask',5000)
        for _ in range(129):step(f,'IndoorAiCfgTask')
        check(f.var('IndoorAiCfgShadow',index=8,width=2)==20 and f.var('IndoorAiCfgDirty')==0,
              f'{profile} AI latest update eventually persisted')
        f.var('IndoorParameterSaveState',2);before=f.var('IndoorAiStState')
        step(f,'IndoorAiCfgTask')
        check(f.var('IndoorAiStState')==before,f'{profile} AI yields to normal parameter writer')
        f.var('IndoorParameterSaveState',0);f.var('IndoorAiStState',1);f.p(134,70)
        step(f)
        check(f.var('IndoorParameterSaveState')==0,f'{profile} normal parameter writer yields to AI')
    out=PACKAGE/'ARM_regression.json'
    out.write_text(json.dumps({'checks':checks,'count':len(checks)},ensure_ascii=False,indent=2),'utf-8')
    print('PASS',len(checks),'actual ARM checks; report',out)

if __name__=='__main__':run()
