"""Exercise new-only indoor AI initialization/storage against the built ARM image."""
import hashlib
import json
from test_defrost_lifecycle_arm import Firmware, IN, ROOT
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_PC, UC_ARM_REG_LR

passed=[]
OFFSETS=[1237+12*ch for ch in range(5)]
LEGACY=[499,498,497,496,457]


def check(ok,label):
    assert ok,label
    passed.append(label)
    print('PASS',label)


def attach_eeprom(f, memory):
    def read(uc,a,n,data):
        dest=uc.reg_read(UC_ARM_REG_R0)
        count=uc.reg_read(UC_ARM_REG_R1)
        source=uc.reg_read(UC_ARM_REG_R2)
        assert source+count<=len(memory)
        uc.mem_write(dest,bytes(memory[source:source+count]))
        uc.reg_write(UC_ARM_REG_R0,1)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    def write(uc,a,n,data):
        value=uc.reg_read(UC_ARM_REG_R0)&255
        address=uc.reg_read(UC_ARM_REG_R1)
        assert address<len(memory)
        memory[address]=value
        uc.reg_write(UC_ARM_REG_R0,1)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    for name,fn in [('CI2C_ReadByte',read),('CI2C_WriteByte',write)]:
        a=f.symbols[name][0]&~1
        f.uc.hook_add(UC_HOOK_CODE,fn,begin=a,end=a)


def main():
    access=Firmware(IN)
    for a in LEGACY:
        check(access.call('ParamCanWriteFromHMI',a,0)==0,
              f'retired AI calibration address {a} rejects HMI writes')
    check(access.call('ParamCanWriteFromHMI',495,35)==1,
          'NTC0 calibration at 495 remains writable')
    check(all(access.call('ParamCanWriteFromHMI',a,10)==1 for a in OFFSETS),
          'all five new AI offsets remain writable')
    memory=bytearray(b'\xff'*4096)
    f=Firmware(IN)
    attach_eeprom(f,memory)
    for i,a in enumerate(LEGACY):f.p(a,100+i*20)
    f.p(495,35)
    reads=[]
    base=f.symbols['Parameter'][0]
    def watch(uc,access,address,size,value,data):
        if any(address<base+2*a+2 and address+size>base+2*a for a in LEGACY):
            reads.append((address,size))
    hook=f.uc.hook_add(UC_HOOK_MEM_READ,watch)
    f.var('Systick_1ms',6000)
    f.call('IndoorAiCfgTask')
    check([f.p(a) for a in OFFSETS]==[0]*5,
          'blank EEPROM initializes every new AI offset to zero despite poisoned legacy slots')
    check(not reads,'initialization never reads retired AI calibration addresses')
    f.uc.hook_del(hook)
    check(f.p(495)==35,'AI initialization preserves NTC0 calibration at 495')

    wanted=[12,-23,34,-45,56]
    for a,v in zip(OFFSETS,wanted):f.p(a,v)
    f.var('Systick_1ms',6100);f.call('IndoorAiCfgTask')
    f.var('Systick_1ms',8099);f.call('IndoorAiCfgTask')
    check(memory==bytearray(b'\xff'*4096),
          'new calibration is not prematurely persisted before the stable interval')
    for t in range(8100,9301,8):
        f.var('Systick_1ms',t);f.call('IndoorAiCfgTask')
    check(f.var('IndoorAiCfgDirty')==0 and f.var('IndoorAiStState')==0,
          'new calibration completes normal two-slot EEPROM write and verification')

    reboot=Firmware(IN)
    attach_eeprom(reboot,memory)
    for a in LEGACY:reboot.p(a,-321)
    reboot.var('Systick_1ms',6000);reboot.call('IndoorAiCfgTask')
    check([reboot.p(a) for a in OFFSETS]==[v&65535 for v in wanted],
          'reboot restores all signed new offsets without importing retired values')
    for ch in range(5):
        b=1229+12*ch
        for delta,value in [(0,1),(2,0),(3,100),(4,0),(5,1000),(9,0)]:reboot.p(b+delta,value)
        check(reboot.call('IndoorScaleAiChannel',ch,500)==500+wanted[ch],
              f'AI{ch} runtime conversion uses its new offset')
    # Both record CRCs invalid: no old-value fallback is allowed.
    memory[1152+125]^=1
    invalid=Firmware(IN)
    attach_eeprom(invalid,memory)
    for a in LEGACY:invalid.p(a,444)
    invalid.var('Systick_1ms',6000);invalid.call('IndoorAiCfgTask')
    check([invalid.p(a) for a in OFFSETS]==[0]*5,
          'invalid new-format storage falls back to zero, never to retired calibration')
    invalid.uc.mem_map(0x22000000,0x100000)  # SRAM bit-band output aliases used by initialization.
    invalid.call('ParameterInit')
    check(all(invalid.var('Parameter_min',index=a,width=2)==0 and
              invalid.var('Parameter_max',index=a,width=2)==0 and
              invalid.var('Parameter_def',index=a,width=2)==0 for a in LEGACY),
          'retired slots have no calibration range or defaults while EEPROM layout remains fixed')
    result={'checks_passed':len(passed),'checks':passed,
            'firmware_sha256':hashlib.sha256((ROOT/IN).read_bytes()).hexdigest(),
            'scope':'ARM initialization, conversion and simulated EEPROM reboot; no hardware access'}
    (ROOT/'.codex-tmp/indoor_ai_retirement_result.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(len(passed),'AI retirement checks passed')


if __name__=='__main__':main()
