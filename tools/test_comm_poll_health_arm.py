"""Offline UART5 scheduling/heartbeat regressions against both timing profiles."""
import json
from test_defrost_lifecycle_arm import Firmware, ROOT
from audit_gateway_readback_arm import rtu_frame
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC

checks=[]
def check(ok,label):
    assert ok,label
    checks.append(label); print('PASS',label)
def fixture(profile):
    f=Firmware(f'.codex-tmp/sequence_timing_v1047_v1238_20261104/{profile}/PSC330_V10.47_{profile}.axf')
    f.uc.mem_map(0x22000000,0x100000)
    f.call('ParameterInit'); f.p(214,3); f.p(304,0)
    sent=[]
    def intercept(uc,a,z,user):
        if a==f.symbols['StartUart5SendData'][0]&~1:
            frame=bytes(uc.mem_read(f.symbols['ucUart5Buff'][0],f.var('ucUart5SendLen')))
            sent.append(frame)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    for name in ['StartUart5SendData','UART5Init']:
        a=f.symbols[name][0]&~1;f.uc.hook_add(UC_HOOK_CODE,intercept,begin=a,end=a)
    return f,sent

def receive(f,frame):
    f.uc.mem_write(f.symbols['ucUart5Buff'][0],frame)
    f.var('ucUart5ReceLen',len(frame));f.call('ModuleReciData')
    f.var('Systick_1ms',f.var('Systick_1ms')+10);f.call('ModuleReciData')

def establish(f,addr,count=1,fn=3):
    f.var('Systick_1ms',10000)
    b=bytes([1,fn,addr>>8,addr&255,count>>8,count&255])
    f.uc.mem_write(f.symbols['ucUart5Buff'][0],b)
    f.call('PSC316Gateway_NoteTransmit')
    f.var('UnitCommErr',1,1,2)

for profile in ['PRODUCTION','BENCH_ONLY_3S']:
    f,sent=fixture(profile)
    for i in range(80):
        f.var('Systick_1ms',10000+i*100);f.call('ModuleSendData')
    check(sent and not any(b[0]==21 for b in sent),profile+': absent optional controller is never polled')
    check(any(b[0]==1 for b in sent) and any(b[0]==2 for b in sent),profile+': both outdoor units still scheduled')
    f.p(304,1)
    for i in range(20):f.call('ModuleSendData')
    check(any(b[0]==21 for b in sent),profile+': configured valve controller retains polling')
    for addr,count,fn,kind in [(1400,10,16,'control ACK'),(1602,6,3,'runtime'),(38,1,3,'capability')]:
        f,_=fixture(profile);establish(f,addr,count,fn)
        payload=bytes([1,16,addr>>8,addr&255,0,count]) if fn==16 else bytes([1,3,count*2])+bytes(count*2)
        receive(f,rtu_frame(payload))
        check(f.var('PSC316UnitLastRespTick',index=0,width=8)==10010,profile+': '+kind+' refreshes heartbeat')
        check(f.var('UnitCommErr',index=1,width=2)==0,profile+': '+kind+' clears current offline status')
    for bad in ['CRC','unit','count']:
        f,_=fixture(profile);establish(f,38)
        frame=rtu_frame(bytes([2 if bad=='unit' else 1,3,4 if bad=='count' else 2])+bytes(4 if bad=='count' else 2))
        if bad=='CRC':frame=frame[:-1]+bytes([frame[-1]^1])
        receive(f,frame)
        check(f.var('PSC316UnitLastRespTick',index=0,width=8)==0,profile+': bad '+bad+' cannot refresh heartbeat')
        check(f.var('UnitCommErr',index=1,width=2)==1,profile+': bad '+bad+' cannot clear offline')
    f,_=fixture(profile)
    f.var('PSC316UnitLastRespTick',1,0,8); f.var('Systick_1ms',10000)
    for i in range(8):f.call('ModuleSendData')
    check(f.var('UnitCommErr',index=1,width=2)==1,profile+': genuinely silent outdoor unit still goes offline')
print(len(checks),'checks passed')
(ROOT/'.codex-tmp/sequence_timing_v1047_v1238_20261104/comm_poll_test_result.json').write_text(json.dumps({'checks_passed':len(checks),'checks':checks},indent=2)+'\n','utf-8')
