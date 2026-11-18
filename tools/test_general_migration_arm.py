"""Positive migration regressions against freshly built Keil ARM firmware.

No serial, probes, real EEPROM writes or physical outputs are accessed.
"""
import hashlib
import json
from test_defrost_lifecycle_arm import Firmware, IN, OUT, ROOT, outdoor, tick, indoor
from audit_general_baseline_arm import parameters, suppress_tx
from audit_gateway_readback_arm import rtu_frame
from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2

checks = []


def check(ok, label):
    assert ok, label
    checks.append(label)
    print('PASS', label)


def context(f, addr, count=1, unit=1, function=3):
    f.uc.mem_write(f.symbols['ucUart5Buff'][0],
                   bytes((unit, function, addr >> 8, addr & 255, count >> 8, count & 255)))
    f.call('PSC316Gateway_NoteTransmit')


def response(f, values, unit=1, bad_crc=False):
    payload = bytes((unit, 3, len(values)*2)) + b''.join(
        (v & 65535).to_bytes(2, 'big') for v in values)
    frame = rtu_frame(payload)
    if bad_crc:
        frame = frame[:-1] + bytes((frame[-1] ^ 1,))
    f.uc.mem_write(f.symbols['ucUart5Buff'][0], frame)
    f.var('ucUart5ReceLen', len(frame))
    f.call('ModuleReciData')
    f.var('Systick_1ms', f.var('Systick_1ms') + 10)
    f.call('ModuleReciData')


def pending():
    f = Firmware(IN)
    f.p(214, 2)
    f.var('Systick_1ms', 36000)
    f.var('PSC316SetMirror', 1, 2, 2)
    assert f.call('PSC316Gateway_HMIWrite', 1832, 0) == 1
    job = f.symbols['PSC316WriteJob'][0]
    f.write(job+1, 2, 1)  # The scheduler requests target readback in phase 2.
    return f, job


def main():
    f = Firmware(IN)
    base, size = f.symbols['Parameter']
    writes = []
    f.uc.hook_add(UC_HOOK_MEM_WRITE, lambda u,a,p,n,v,d:
                  writes.append(p) if base+size <= p < base+size+16 else None)
    f.uc.mem_write(base+size, b'\xa5'*16)
    f.call('PSC316Gateway_PublishToHMI')
    check(size == 2892*2 and not writes and bytes(f.uc.mem_read(base+size,16)) == b'\xa5'*16,
          'fourth outdoor fan mirror stays within Parameter allocation')
    check(f.call('ParamCanWriteFromHMI', 1229, 1) == 1,
          'valid indoor AI configuration is writable')
    suppress_tx(f)
    buf = f.symbols['ucUart6Buff'][0]
    f.uc.mem_write(buf, bytes((1,6,3,32,0x12,0x34,0,0)))
    f.var('ucUart6ReceLen', 8)
    f.call('ModbusUart6Fun6')
    check(f.p(800) == 0, 'UART6 cannot write a protected status register')
    for path in (IN, OUT):
        f = Firmware(path)
        f.uc.mem_map(0x22000000, 0x100000)
        f.call('ParameterInit')
        signed = lambda v: v-65536 if v & 32768 else v
        check(all(signed(f.var('Parameter_min',index=i,width=2)) <=
                  signed(f.var('Parameter_def',index=i,width=2)) <=
                  signed(f.var('Parameter_max',index=i,width=2)) for i in range(500)),
              path.split('/')[0] + ': saved defaults remain inside limits')

    for wrong in ('register', 'unit', 'crc', 'expired'):
        f, job = pending()
        context(f, 38 if wrong == 'register' else 167)
        f.write(job+1, 3, 1)
        if wrong == 'expired':
            f.var('Systick_1ms', f.var('Systick_1ms')+600)
        response(f, [0], unit=2 if wrong == 'unit' else 1, bad_crc=wrong=='crc')
        check(f.var('PSC316WriteState',index=0,width=1) != 2 and
              f.var('PSC316SetMirror',index=2,width=2) == 1,
              wrong + ' response cannot falsely confirm enable write')
    f,job = pending()
    context(f,167)
    f.write(job+1,3,1)
    response(f,[0])
    check(f.var('PSC316WriteState',index=0,width=1) == 2 and
          f.var('PSC316SetMirror',index=2,width=2) == 0,
          'matching requested readback confirms the target write')
    f,job = pending()
    check(f.call('PSC316Gateway_HMIWrite',1833,1) == 0,
          'busy gateway rejects a different write instead of acknowledging it')
    f=Firmware(IN)
    f.var('Systick_1ms',36000)
    context(f,1400,10,function=16)
    frame=rtu_frame(bytes((1,16,5,120,0,10)))
    f.uc.mem_write(f.symbols['ucUart5Buff'][0],frame)
    f.var('ucUart5ReceLen',8);f.call('ModuleReciData')
    f.var('Systick_1ms',36010);f.call('ModuleReciData')
    check(f.var('PSC316CtrlShadowValid',index=0,width=1)==1,
          'control shadow becomes valid only after the matching RTU write ACK')
    f=Firmware(IN)
    context(f,1400,10,function=16)
    f.var('Systick_1ms',600);f.call('PSC316BusMaySend')
    check(f.var('PSC316CtrlShadowValid',index=0,width=1)==0,
          'lost control ACK leaves the shadow invalid so scheduler can retransmit')

    f = Firmware(IN)
    f.p(214,2);f.p(540,1)
    f.var('ReadBackFlag',1,1,2)
    f.uc.mem_map(0x22000000,0x100000)
    f.call('W5070Disp')
    f.field(True,1,'TempCheck',6,50)
    f.call('W5070Disp')
    check(f.p(746) == 50 and f.field(True,1,'TempCheck',6) == 50,
          'late calibration feedback updates an unchanged page without reverse write')
    f.p(746,60);f.call('W5070Disp')
    check(f.field(True,1,'TempCheck',6) == 50 and f.var('PSC316WriteJob',width=1) == 1,
          'page edit stays pending while confirmed calibration cache remains intact')

    f=Firmware(IN)
    parameters(f,{709:2,236:1,128:1,332:1,127:1,129:1,214:2,250:1,251:1,
                  512:-10,346:300,738:250,739:250,120:20})
    f.call('HeatControl_UP');f.call('IndoorEnforceConfiguredOutputDisable')
    check(f.var('DA',index=0,width=2) == 0 and f.p(890) == 0,
          'winter minimum cannot bypass auxiliary full-load permission')
    f=Firmware(IN)
    parameters(f,{709:2,236:1,128:2,512:100,738:230,739:250,120:20})
    f.call('HeatControl_UP')
    check(f.p(890) == 0, '23 C does not force full heat under literal WD/2 boundary')

    f=Firmware(IN)
    parameters(f,{236:1,128:5,129:1,333:4})
    for name,val in [('IndoorHeatAnalogMode',4),('IndoorPreheatAnalogMode',4),
                     ('IndoorHeatAnalogDemand',600),('IndoorPreheatAnalogDemand',800),
                     ('IndoorHeatScrRegion',1),('IndoorPreheatScrRegion',2)]:f.var(name,val)
    f.call('IndoorApplyHeatAnalogOutputs')
    check(f.var('DA',index=0,width=2)==750 and f.var('DA',index=1,width=2)==500 and
          [f.var('output',index=i,width=1) for i in (0,1,2,13,14,15)] == [1,0,0,1,1,0],
          'independent SCR heat/preheat drive one AO and two DO groups each with residual power')

    f=Firmware(OUT)
    parameters(f,{80:0,800:1})
    f.var('output',1,1,1)
    check(f.call('EEVSpecFaultRequiresClose',0)==0,
          'healthy compressor keeps a shared EEV when the other compressor faults')
    f.var('UnitLevelFault',1)
    check(f.call('EEVSpecFaultRequiresClose',0)==1,
          'unit fault still closes a shared EEV')
    f=Firmware(OUT)
    f.var('BoardAddressSet',1)
    parameters(f,{1400:1,45:15})
    f.var('CompStopTime',120,0,4)
    f.var('output',1,2,1)
    for ms in (0,15000):
        f.var('Systick_1ms',ms);f.call('ModuleCompAction')
    check(f.var('Comp',index=0,width=1)==0, 'actual pre-ventilation does not finish early')
    f.var('Systick_1ms',16000);f.call('ModuleCompAction')
    check(f.var('Comp',index=0,width=1)==1, 'actual pre-ventilation permits start after configured delay')

    f=outdoor()
    f.p(153,1);f.call('DefrostProcess')
    check(f.var('Comp',index=1,width=1)==0 and f.p(1420)==8,
          'newly disabled defrost circuit stops while healthy circuit continues')
    f.var('X_00',1);f.call('DefrostProcess');tick(f,59)
    check(f.p(1420)==7, 'dynamic defrost disable retains recovery before 60 seconds')
    tick(f,1)
    check(f.p(1420)==0, 'dynamic defrost disable completes recovery at 60 seconds')

    f=indoor()
    f.field(True,1,'CompControl',0,1)
    f.call('CompStartStateUpdate')
    f.var('Systick_1ms',60000);f.call('CompStartStateUpdate')
    check(f.field(True,1,'CompControl',0)==0 and f.call('CompStartInhibited',1,0)==1,
          'unconfirmed start times out and is inhibited for a retry interval')
    f.p(251,0)
    for i in range(10):f.var('CompMinStopCount',1000,i,4)
    f.var('Systick_1ms',90000);f.call('CompEnvFullLoad')
    check(f.field(True,2,'CompControl',0)==1,
          'timed-out first unit does not block a healthy later unit in full load')
    f=indoor()
    f.field(True,1,'CompControl',0,1);f.field(False,1,'CompStatus',0,3)
    f.call('CompStartStateUpdate')
    f.field(False,1,'CompStatus',0,0);f.field(False,1,'CanDefrost',0,7)
    f.call('CompNormalStopAction')
    check(f.field(True,1,'CompControl',0)==0,
          'normal shutdown retires already stopped defrost requests during recovery')
    f=Firmware(IN)
    check(f.call('PSC316UnitSettingsReady',1)==0,
          'unknown outdoor settings cannot authorize a new compressor start')

    f=Firmware(OUT)
    f.uc.mem_map(0x22000000,0x100000);f.call('ParameterInit')
    def no_io(uc,a,n,user):uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    a=f.symbols['StartUart5SendData'][0]&~1
    f.uc.hook_add(UC_HOOK_CODE,no_io,begin=a,end=a)
    buf=f.symbols['ucUart5Buff'][0]
    frame=rtu_frame(bytes((1,6,0,152,0,1)))
    f.uc.mem_write(buf,frame);f.var('ucUart5ReceLen',len(frame));f.call('ModbusUart5Fun6')
    check(bytes(f.uc.mem_read(buf,8))==frame and f.p(152)==1,
          'outdoor FC06 response CRC matches standard RTU byte order')
    f.p(165,1);f.p(166,3)
    frame=rtu_frame(bytes((1,16,0,165,0,2,4,0,2,0,99)))
    f.uc.mem_write(buf,frame);f.var('ucUart5ReceLen',len(frame));f.call('ModbusUart5Fun16')
    check(f.p(165)==1 and f.p(166)==3,
          'outdoor block with an invalid later value makes no partial configuration write')
    frame=rtu_frame(bytes((1,16,0,165,0,2,4,0,2)))
    f.uc.mem_write(buf,frame);f.var('ucUart5ReceLen',len(frame));f.call('ModbusUart5Fun16')
    check(f.p(165)==1 and f.p(166)==3,
          'truncated FC16 payload makes no configuration write')

    f=Firmware(OUT)
    body=bytes.fromhex('c302000000070000006f000000de0000014d')
    f.uc.mem_write(0x20060000,body)
    crc=f.call('CompressorRuntimeCRC16',0x20060000,len(body))
    memory=bytearray(b'\xff'*4096)
    record=body+crc.to_bytes(2,'big');memory[1024:1024+len(record)]=record
    def read_eeprom(uc,a,n,user):
        dest=uc.reg_read(UC_ARM_REG_R0);count=uc.reg_read(UC_ARM_REG_R1);source=uc.reg_read(UC_ARM_REG_R2)
        uc.mem_write(dest,bytes(memory[source:source+count]))
        uc.reg_write(UC_ARM_REG_R0,1);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    a=f.symbols['CI2C_ReadByte'][0]&~1
    f.uc.hook_add(UC_HOOK_CODE,read_eeprom,begin=a,end=a)
    f.call('CompressorRuntimeInit')
    check(f.var('OutdoorTotalRunSeconds')==333 and
          [f.var('CompTotalRunSeconds',index=i,width=4) for i in range(2)]==[111,222],
          'V2 EEPROM record restores outdoor runtime as well as both compressor totals')
    values=[f.var('R410ATemp',index=i,width=2) for i in range(f.symbols['R410ATemp'][1]//2)]
    values=[v-65536 if v>=32768 else v for v in values]
    check(all(a<=b for a,b in zip(values[20:],values[21:])),
          'R410A effective saturation-temperature table is monotonic')

    f=Firmware(IN)
    parameters(f,{709:2,236:1,333:1,374:0,512:-100,356:0,357:-50,966:1})
    f.call('PreHeatControl')
    check(f.var('DA',index=1,width=2)==1000,
          'main heat fault does not suppress an independent healthy preheater')
    f=Firmware(IN)
    parameters(f,{709:2,236:1,128:2,738:0,739:250,968:1})
    f.call('HeatControl_UP')
    check(f.var('DA',index=0,width=2)==1000,
          'preheater fault does not suppress an independent healthy main heater')
    f=Firmware(IN)
    f.uc.mem_map(0x22000000,0x100000)
    parameters(f,{709:2,236:1,333:4,374:1,512:-100})
    f.call('PreHeatControl')
    check(f.p(940)&128 and f.var('DA',index=1,width=2)==0,
          'post-preheat PID with SCR is diagnosed and cannot silently use ambient control')

    f=Firmware(IN)
    parameters(f,{236:2,136:1})
    f.var('NTC_AD',32767,0,2);f.call('Get_temp16')
    check(f.var('SensorStatus',index=5,width=1)==0,
          'optional room NTC can be masked in ventilation')
    f.p(236,0);f.call('Get_temp16')
    check(f.var('SensorStatus',index=5,width=1)==1,
          'a room NTC required for cooling cannot be masked')
    f.p(139,1)
    f.var('NTC_AD',32767,4,2);f.call('Get_temp16')
    check(f.var('SensorStatus',index=9,width=1)==1,
          'evaporating NTC protection cannot be masked')
    f=Firmware(IN)
    parameters(f,{457:100,496:90,497:80,498:70,499:60,495:50})
    f.call('IndoorAiCfgSeedDefaults')
    check(all(f.p(1237+12*ch)==0 for ch in range(5)),
          'new AI defaults never import any retired calibration slot')
    f.p(495,-50);f.call('IndoorAiCfgSeedDefaults')
    check(f.p(1285)==0 and f.p(495)==((-50)&65535),
          'AI4 default calibration is independent of the preserved NTC0 calibration')

    f=Firmware(IN)
    parameters(f,{236:0,329:3,340:50,341:30,342:80,617:1,1265:1,290:1,291:10})
    f.var('UserPump',1);f.var('uc1s',1)
    for _ in range(20):f.call('FanAction')
    check(f.p(954)==1 and f.p(926)==500,
          'bad automatic supply feedback holds configured initial demand without feedback integration')
    f.p(617,0)
    for _ in range(9):f.call('FanAction')
    check(f.p(954)==2, 'supply feedback recovery waits the full ten-second confirmation')
    f.call('FanAction')
    check(f.p(954)==0, 'supply feedback returns to closed loop after ten seconds')

    f=Firmware(OUT)
    parameters(f,{165:1,166:3,107:1})
    f.var('Comp',1,0,1);f.var('output',1,0,1)
    f.var('OutdoorFanRegulationStop',1)
    f.call('OutdoorProtectOutputLimit')
    check(f.var('output',index=0,width=1)==1,
          'authorized automatic pressure-regulation stop preserves a running compressor')
    f.var('OutdoorFanRegulationStop',0)
    f.call('OutdoorProtectOutputLimit')
    check(f.var('output',index=0,width=1)==0,
          'unexplained absence of airflow still blocks compressor final output')
    f=Firmware(OUT)
    parameters(f,{165:1,166:0,1300:1})
    f.var('output',1,2,1);f.var('output',1,7,1)
    f.call('OutdoorProtectOutputLimit')
    check(not(f.var('output',index=2,width=1) and f.var('output',index=7,width=1)),
          'manual mode cannot energize both speeds of the same fan')

    f=Firmware(OUT)
    parameters(f,{166:2,45:15,107:1,872:1,1463:300,176:50})
    f.var('output',1,2,1);f.var('OutdoorVfdSpeed',300)
    f.call('OutdoorFanSyncVfdAnalogOutput')
    f.var('Systick_1ms',1999);f.call('OutdoorFanSyncVfdAnalogOutput')
    check(f.var('DA',index=0,width=2)==0, 'VFD keeps analog zero until two seconds after real DO enable')
    f.var('Systick_1ms',2000);f.call('OutdoorFanSyncVfdAnalogOutput')
    check(f.var('DA',index=0,width=2)==600, 'VFD applies proportional demand after DO enable delay')

    for path in (IN,OUT):
        f=Firmware(path)
        if path==IN:
            parameters(f,{16:1,368:5,369:100,370:0,367:20,371:3})
        else:
            parameters(f,{198:50,199:5,202:20,203:1,204:100,205:0,206:3})
        f.var('uc100ms',1)
        for sample in range(3):
            f.var('EEVSpecPidCount',9,0,4)
            args=(0,50,50,130,0x20060000) if path==IN else (0,50,130,0x20060000)
            step=f.call('EEVSpecPidStep',*args)
            check(step==0xfffffffd,
                  path.split('/')[0]+f': high evaporation overrides SH dead band, respects 3-step limit (sample {sample+1})')

    result={'checks_passed':len(checks),'checks':checks,
            'firmware_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (IN,OUT)},
            'scope':'ARM code with injected IO, no physical bench acceptance'}
    (ROOT/'.codex-tmp/general_migration_arm_result.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(len(checks),'migration checks passed')


if __name__=='__main__':main()
