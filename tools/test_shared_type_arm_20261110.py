"""Actual 330/316 ARM handlers and broadcast construction; no hardware access."""
import hashlib
import json
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR

PACKAGE = ROOT / '.codex-tmp/shared_type_v1058_20261110'
DEST = ROOT / '测试证据/机型风机全局共享_20261110'
ROWS = []

def check(name, got, want):
    ROWS.append(dict(name=name, observed=got, expected=want, passed=got == want))
    assert got == want, ROWS[-1]

def rtu(data):
    crc = 0xffff
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xa001 if crc & 1 else 0)
    return data + crc.to_bytes(2, 'little')

def hooks(f, names):
    sent = []
    def intercept(uc, address, size, user):
        for name in names:
            if address == (f.symbols[name][0] & ~1) and name.startswith('Start'):
                port = name[len('StartUart')]
                sent.append(bytes(uc.mem_read(f.symbols[f'ucUart{port}Buff'][0],
                                             f.var(f'ucUart{port}SendLen'))))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    for name in names:
        addr = f.symbols[name][0] & ~1
        f.uc.hook_add(UC_HOOK_CODE, intercept, begin=addr, end=addr)
    return sent

def hmi(f, address, values, multi=False):
    if multi:
        payload = bytes([1,16])+address.to_bytes(2,'big')+len(values).to_bytes(2,'big')
        payload += bytes([len(values)*2])+b''.join((v&65535).to_bytes(2,'big') for v in values)
    else:
        payload = bytes([1,6])+address.to_bytes(2,'big')+(values[0]&65535).to_bytes(2,'big')
    frame = rtu(payload)
    f.uc.mem_write(f.symbols['ucUart1Buff'][0], frame)
    f.var('ucUart1ReceLen', len(frame))
    f.call('ModbusUart1Fun16' if multi else 'ModbusUart1Fun6')

def mirror(f, unit, offset, values):
    for j,v in enumerate(values):
        f.var('PSC316SetMirror', v, unit*42+offset+j, 2)
    f.var('PSC316SetValid', 1, unit, 1)

def legacy_run(profile):
    folder = PACKAGE/profile
    path = folder/f'PSC330_V10.58_{profile}.axf'
    outpath = folder/f'PSC316_V12.40_{profile}.axf'
    def new():
        f = Firmware(path)
        f.p(214,5)
        hooks(f, ('StartUart1SendData','StartUart5SendData','UART5Init'))
        return f
    f = new()
    f.p(1319,1)
    for a,low,default,high in ((1340,30,50,50),(1341,0,5,30),(1342,1,10,20)):
        for v in dict.fromkeys((low,default,high,low-1,high+1,-1)):
            f.p(a,default)
            hmi(f,a,[v])
            check(f'{profile}/FC06/{a}/{v}',f.p(a),v if low<=v<=high else default)
    hmi(f,1340,[40,0,15],True)
    check(f'{profile}/FC16/valid-including-zero',[f.p(a) for a in range(1340,1343)],[40,0,15])
    hmi(f,1340,[45,31,10],True)
    check(f'{profile}/FC16/invalid-atomic',[f.p(a) for a in range(1340,1343)],[40,0,15])
    hmi(f,1319,[0])
    for a in range(1340,1343):
        old=f.p(a);hmi(f,a,[30 if a==1340 else 5])
        check(f'{profile}/shared-off/source-readonly/{a}',f.p(a),old)
    for enabled in (0,1):
        f.p(1319,enabled)
        for unit in range(4):
            for p,value in ((176,45),(177,0),(178,15)):
                address=1830+48*unit+p-165
                f.var('PSC316WriteJob',0,width=1)
                accepted=f.call('PSC316Gateway_HMIWrite',address,value)
                check(f'{profile}/unit{unit+1}/{p}/shared{enabled}/accepted',accepted,1-enabled)
                if enabled:
                    check(f'{profile}/unit{unit+1}/{p}/error',f.var('PSC316WriteError',index=unit,width=1),9)
            payload=bytes([0,45,0,0,0,15]);ptr=0x20060000;f.uc.mem_write(ptr,payload)
            f.var('PSC316WriteJob',0,width=1)
            check(f'{profile}/unit{unit+1}/block/shared{enabled}',
                  f.call('PSC316Gateway_HMIWriteBlock',1830+48*unit+11,3,ptr),2 if enabled else 1)

    # Cold-start and upgrade fixtures: an old shared source may be nonzero
    # while the newly allocated RAM words are zero. Never broadcast zero max.
    for first_valid in range(4):
        f=new();f.p(1331,180)
        f.call('PSC316SharedMirrorFromUnit1')
        check(f'{profile}/seed{first_valid}/wait-for-mirror',f.var('PSC316SharedVfdSeeded'),0)
        mirror(f,first_valid,11,[45,0,15])
        f.call('PSC316SharedMirrorFromUnit1')
        check(f'{profile}/seed{first_valid}/adopt-existing',[f.p(a) for a in range(1340,1343)],[45,0,15])
        f.p(1340,40);mirror(f,first_valid,11,[50,10,20])
        f.call('PSC316SharedMirrorFromUnit1')
        check(f'{profile}/seed{first_valid}/retain-shared-edit',f.p(1340),40)
        mirror(f,0,11,[35,5,1]);f.p(1319,0)
        f.call('PSC316SharedMirrorFromUnit1')
        check(f'{profile}/seed{first_valid}/off-mirror-unit1',[f.p(a) for a in range(1340,1343)],[35,5,1])
    f=new();hmi(f,1319,[1]);hmi(f,1340,[40,0,15],True)
    f.call('PSC316SharedMirrorFromUnit1')
    check(f'{profile}/before-first-mirror/legal-HMI-preserved',[f.p(a) for a in range(1340,1343)],[40,0,15])

    f=new();sent=hooks(f,('StartUart5SendData','UART5Init'))
    f.p(1331,180)
    f.var('ModuleNum',5);f.var('SendParaAddr1',10)
    f.call('ModuleSendData')
    check(f'{profile}/unseeded/no-vfd-broadcast',int.from_bytes(sent[-1][2:4],'big'),1)
    mirror(f,0,5,[180,180,300,150,70,50,45,0,15,30,30,60,100,30,4,10,-20,100,30,35,400,4,3])
    f.call('PSC316SharedMirrorFromUnit1')
    sources=[1331,1332,1333,1334,1335,1336,1340,1341,1342,1337,1338,1339]+list(range(1389,1400))
    values=[180,180,300,150,70,50,45,0,15,30,30,60,100,30,4,10,-20,100,30,35,400,4,3]
    for a,v in zip(sources,values):f.p(a,v)
    frames=[]
    for step,address,count,expected in ((9,170,6,values[:6]),(10,176,6,values[6:12]),(11,182,11,values[12:])):
        f.var('ModuleNum',5);f.var('SendParaAddr1',step)
        f.call('ModuleSendData');frame=sent[-1];frames.append(frame)
        observed=[int.from_bytes(frame[7+2*j:9+2*j],'big') for j in range(count)]
        check(f'{profile}/broadcast/{address}/header',list(frame[:7]),[254,16,0,address,0,count,count*2])
        check(f'{profile}/broadcast/{address}/payload',observed,[v&65535 for v in expected])
        check(f'{profile}/broadcast/{address}/crc',frame[-2:].hex(),rtu(frame[:-2])[-2:].hex())
    # Execute the existing outdoor receiver on each captured 330 broadcast.
    for unit in range(1,5):
        o=Firmware(outpath);o.call('ParameterInit');hooks(o,('StartUart5SendData',))
        o.var('BoardAddressSet',unit)
        for frame in frames:
            o.uc.mem_write(o.symbols['ucUart5Buff'][0],frame)
            o.var('ucUart5ReceLen',len(frame));o.call('ModbusUart5Fun16')
        check(f'{profile}/outdoor{unit}/receive-all23',[o.p(a) for a in range(170,193)],[v&65535 for v in values])
    f.p(1319,0);f.var('ModuleNum',5);f.var('SendParaAddr1',10)
    f.call('ModuleSendData')
    check(f'{profile}/shared-off/no-extended-broadcast',int.from_bytes(sent[-1][2:4],'big'),1)


def run(profile):
    legacy_run(profile)
    folder=PACKAGE/profile
    path=folder/f'PSC330_V10.58_{profile}.axf'
    def new(pair=(0,1)):
        f=Firmware(path);f.p(214,5)
        hooks(f,('StartUart1SendData','StartUart5SendData','UART5Init'))
        mirror(f,0,0,list(pair));mirror(f,0,11,[50,5,10])
        f.call('PSC316SharedMirrorFromUnit1');return f
    f=Firmware(path);f.p(214,5)
    hooks(f,('StartUart1SendData','StartUart5SendData','UART5Init'))
    f.p(1331,180);mirror(f,1,0,[2,4]);mirror(f,1,11,[50,5,10])
    f.call('PSC316SharedMirrorFromUnit1')
    check(f'{profile}/type_seed/not_unit2',f.var('PSC316SharedTypeSeeded'),0)
    check(f'{profile}/type_seed/unready_source_rejected',f.call('PSC316SharedTypeCanWrite'),0)
    sent=hooks(f,('StartUart5SendData','UART5Init'))
    f.var('ModuleNum',5);f.var('SendParaAddr1',13);f.call('ModuleSendData')
    check(f'{profile}/type_seed/unready_no_broadcast',int.from_bytes(sent[-1][2:4],'big'),1)
    mirror(f,0,0,[0,0]);f.call('PSC316SharedMirrorFromUnit1')
    check(f'{profile}/type_seed/legal_zero_pair',[f.p(1343),f.p(1344),f.var('PSC316SharedTypeSeeded')],[0,0,1])
    for address,values in ((1343,[0,1,2,-1,3]),(1344,[0,1,2,3,4,-1,5])):
        for v in values:
            f=new();old=f.p(address);hmi(f,address,[v])
            high=2 if address==1343 else 4
            check(f'{profile}/type_FC06/{address}/{v}',f.p(address),v if 0<=v<=high else old)
    f=new();hmi(f,1343,[2,4],True)
    check(f'{profile}/type_FC16/legal',[f.p(1343),f.p(1344)],[2,4])
    hmi(f,1343,[1,5],True)
    check(f'{profile}/type_FC16/invalid_atomic',[f.p(1343),f.p(1344)],[2,4])
    for step in (1,2,3,4):
        f=new();f.p(709,step);hmi(f,1343,[2]);hmi(f,1344,[4])
        check(f'{profile}/type_running_step{step}/reject',[f.p(1343),f.p(1344)],[0,1])
    for u in range(1,5):
        for c in range(2):
            for status in (2,3,4):
                f=new();f.field(False,u,'CompStatus',c,status)
                check(f'{profile}/type_running_unit{u}_comp{c}_status{status}/blocked',f.call('PSC316SharedTypeCanWrite'),0)
    for enabled in (0,1):
        f=new();f.p(1319,enabled)
        for unit in range(4):
            for parameter,value in ((165,2),(166,4)):
                f.var('PSC316WriteJob',0,width=1)
                check(f'{profile}/type_gateway/{unit}/{parameter}/shared{enabled}',
                    f.call('PSC316Gateway_HMIWrite',1830+48*unit+parameter-165,value),1-enabled)
            f.var('PSC316WriteJob',0,width=1);ptr=0x20060000;f.uc.mem_write(ptr,bytes([0,2,0,4]))
            check(f'{profile}/type_gateway_block/{unit}/shared{enabled}',
                f.call('PSC316Gateway_HMIWriteBlock',1830+48*unit,2,ptr),2 if enabled else 1)
    f=new((2,4));f.p(1319,0);hmi(f,1343,[0]);hmi(f,1344,[1])
    check(f'{profile}/type_off_sources_readonly',[f.p(1343),f.p(1344)],[2,4])
    mirror(f,0,0,[1,3]);f.call('PSC316SharedMirrorFromUnit1')
    check(f'{profile}/type_off_mirror',[f.p(1343),f.p(1344)],[1,3])
    f=new((2,4));sent=hooks(f,('StartUart5SendData','UART5Init'))
    f.var('ModuleNum',5);f.var('SendParaAddr1',13);f.call('ModuleSendData');frame=sent[-1]
    check(f'{profile}/type_broadcast/frame',frame.hex(),rtu(bytes([254,16,0,165,0,2,4,0,2,0,4])).hex())
    for unit in range(1,5):
        o=Firmware(folder/f'PSC316_V12.40_{profile}.axf');o.call('ParameterInit');hooks(o,('StartUart5SendData',));o.var('BoardAddressSet',unit)
        o.uc.mem_write(o.symbols['ucUart5Buff'][0],frame);o.var('ucUart5ReceLen',len(frame));o.call('ModbusUart5Fun16')
        check(f'{profile}/type_receive/unit{unit}',[o.p(165),o.p(166)],[2,4])
    f.p(709,2);f.var('ModuleNum',5);f.var('SendParaAddr1',13);f.call('ModuleSendData')
    check(f'{profile}/type_running_no_broadcast',int.from_bytes(sent[-1][2:4],'big'),1)


def main():
    DEST.mkdir(exist_ok=True)
    hashes={}
    try:
        for profile in ('PRODUCTION','BENCH_ONLY_3S'):
            m=json.loads((PACKAGE/profile/'manifest.json').read_text('utf8'))
            assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in m['source_inventory'].items())
            assert all(hashlib.sha256((PACKAGE/profile/p).read_bytes()).hexdigest()==h for p,h in m['artifacts'].items())
            hashes.update({str(PACKAGE/profile/p):h for p,h in m['artifacts'].items()})
            run(profile)
    finally:
        result=dict(method='Unicorn actual Keil ARM handlers; UART physical boundary intercepted',
                    hardware_tested=False, artifact_sha256=hashes,
                    source_inventory=m['source_inventory'],
                    rows=ROWS, passed=sum(r['passed'] for r in ROWS), total=len(ROWS))
        (DEST/'arm_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print('ARM',result['passed'],'/',result['total'],flush=True)

if __name__=='__main__':main()
