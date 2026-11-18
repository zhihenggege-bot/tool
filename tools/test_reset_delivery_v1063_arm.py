"""Actual scheduler/CRC receive regression for durable per-unit fault reset."""
import json
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC,UC_ARM_REG_LR

P=ROOT/'.codex-tmp/manual_gate_v1063_v1244_20261113'
OLD=ROOT/'.codex-tmp/manual_gate_v1062_v1244_20261113'

def rtu(data):
    crc=65535
    for v in data:
        crc^=v
        for _ in range(8):crc=(crc>>1)^0xA001 if crc&1 else crc>>1
    return data+crc.to_bytes(2,'little')

class Driver:
    def __init__(self,path,count=2):
        self.f=f=Firmware(path);f.uc.mem_map(0x22000000,0x100000)
        f.p(214,count+1);f.p(540,1);self.sent=[];self.t=10000
        for u in range(4):f.var('PSC316VersionRequestPending',0,u,1)
        def hook(uc,a,size,user):
            if a==f.symbols['StartUart5SendData'][0]&~1:
                self.sent.append(bytes(uc.mem_read(f.symbols['ucUart5Buff'][0],f.var('ucUart5SendLen'))))
                uc.reg_write(UC_ARM_REG_PC,f.symbols['PSC316Gateway_NoteTransmit'][0])
            else:uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        for name in ('StartUart5SendData','UART5Init'):
            a=f.symbols[name][0]&~1;f.uc.hook_add(UC_HOOK_CODE,hook,begin=a,end=a)
    def send(self,unit=None):
        self.t+=1000;self.f.var('Systick_1ms',self.t)
        if unit is not None:self.f.var('ModuleNum',unit,width=1)
        before=len(self.sent);self.f.call('ModuleSendData')
        return self.sent[-1] if len(self.sent)>before else None
    def receive(self,frame):
        f=self.f;f.uc.mem_write(f.symbols['ucUart5Buff'][0],frame)
        f.var('ucUart5ReceLen',len(frame));f.call('ModuleReciData')
        self.t+=10;f.var('Systick_1ms',self.t);f.call('ModuleReciData')
    def ack(self,frame,wrong_unit=False,bad_crc=False):
        payload=bytearray(frame[:6])
        if wrong_unit:payload[0]=2 if payload[0]==1 else 1
        response=rtu(bytes(payload))
        if bad_crc:response=response[:-1]+bytes([response[-1]^1])
        self.receive(response)
    def pending(self,u):
        return self.f.var('PSC316ResetAck',index=u-1,width=2)!=self.f.var('PSC316ResetGeneration',width=2)

def reset_word(frame):
    assert frame[1]==16 and int.from_bytes(frame[2:4],'big')==1400,frame.hex()
    return int.from_bytes(frame[11:13],'big')

def normal_trace(path,count):
    d=Driver(path,count);trace=[]
    for _ in range(450):
        frame=d.send()
        if not frame:continue
        trace.append(frame.hex())
        if frame[0]>=254:continue
        if frame[1] in (6,16):d.ack(frame)
        else:
            n=int.from_bytes(frame[4:6],'big')
            d.receive(rtu(bytes([frame[0],3,n*2])+bytes(n*2)))
    return trace

def main():
    rows=[]
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        new=P/profile/f'PSC330_V10.63_{profile}.axf';old=OLD/profile/f'PSC330_V10.62_{profile}.axf'
        alarm_cases=[]
        alarm_fixture=Driver(new).f
        for manual in (0,1):
            for alarm in (0,1):
                for test in (0,1):
                    alarm_fixture.p(1300,manual);alarm_fixture.p(1318,test);alarm_fixture.p(861,alarm)
                    alarm_fixture.var('output',alarm,5,1)
                    alarm_fixture.call('HandDebugY02Ctrl')
                    actual=alarm_fixture.var('output',index=5,width=1)
                    assert actual==int(bool(alarm or (manual and test)))
                    alarm_cases.append(dict(manual=manual,real_alarm=alarm,manual_alarm_test=test,Y05=actual))
        for count in (2,4):
            assert normal_trace(new,count)==normal_trace(old,count),(profile,count,'normal poll behavior changed')
        d=Driver(new);f=d.f
        f.call('PSC316Gateway_ClearFaultLatch');f.p(1402,0)
        f.var('SendParaAddr3',6,1,1);f.var('PSC316VersionRequestPending',1,0,1)
        frame=d.send(1);assert reset_word(frame)==1 and d.pending(1)
        d.ack(frame,bad_crc=True);assert d.pending(1)
        f.var('PSC316BusActive',0)
        frame=d.send(1);assert reset_word(frame)==1
        d.ack(frame,wrong_unit=True);assert d.pending(1)
        f.var('PSC316BusActive',0)
        frame=d.send(2);assert reset_word(frame)==1;d.ack(frame)
        assert not d.pending(2) and d.pending(1)
        frame=d.send(1);assert reset_word(frame)==1;d.ack(frame);assert not d.pending(1)
        f.var('PSC316VersionRequestPending',0,0,1);f.var('SendParaAddr3',0,1,1)
        cleared=d.send(1);assert reset_word(cleared)==0;d.ack(cleared)
        f.call('PSC316Gateway_ClearFaultLatch');frame=d.send(1)
        generation=f.var('PSC316ResetGeneration',width=2)
        f.call('PSC316Gateway_ClearFaultLatch');d.ack(frame)
        assert f.var('PSC316ResetAck',index=0,width=2)==generation and d.pending(1)
        again=d.send(1);assert reset_word(again)==1;d.ack(again);assert not d.pending(1)
        f.var('PSC316ResetGeneration',65535,width=2);f.call('PSC316Gateway_ClearFaultLatch')
        assert f.var('PSC316ResetGeneration',width=2)==1 and d.pending(1) and d.pending(2)
        row=dict(profile=profile,normal_two_and_four_unit_trace_equal=True,
                 expired_window_delivered=True,bad_crc_rejected=True,wrong_unit_ack_rejected=True,
                 lost_ack_retry=True,per_unit_completion=True,old_ack_cannot_clear_new_request=True,
                 reset_zero_sent_after_delivery=True,generation_wrap=True,alarm_truth_table=alarm_cases,passed=True)
        rows.append(row);print('RESET DELIVERY ARM PASS',profile,flush=True)
    (P/'reset_delivery_ARM_regression.json').write_text(json.dumps(rows,indent=2),encoding='utf8')

if __name__=='__main__':main()
