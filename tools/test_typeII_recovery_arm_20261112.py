"""Actual fan scan and final interlock: preserve running compressors in recovery.

All state/input injection below is confined to offline Unicorn memory. No probe
or serial port is opened. Temperature conversion is explicitly stubbed.
"""
import argparse
import hashlib
import json
from test_defrost_lifecycle_arm import Firmware, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_LR


def fixture(path,ambient,maximum):
    f=Firmware(path)
    for a,v in {1:0,107:1,165:1,166:3,172:300,173:150,176:50,177:5,
                179:30,180:30,1400:1,1403:1,1422:ambient}.items():f.p(a,v)
    for name,value in {'BoardAddressSet':1,'OutdoorFanLastWorkMode':0,
        'OutdoorFanLastUnitType':1,'OutdoorFanLastType':3,'OutdoorFanLastPressureMode':1,
        'OutdoorTypeIIStage':0,'OutdoorTypeIIPendingStage':0,'OutdoorTypeIILowFanOff':1,
        'OutdoorTypeIILowOffCount':30,'OutdoorFanChangeSeconds':100}.items():f.var(name,value)
    for i in (0,1):
        f.var('Comp',1,i,1);f.var('output',1,i,1)
        f.var('OutdoorFanStopTick',50000,i,4);f.var('OutdoorFanStopTickValid',1,i,1)
    def inject(uc,address,size,user):
        value=290 if address==(f.symbols['OutdoorCondTempMin'][0]&~1) else (maximum() if callable(maximum) else maximum)
        uc.reg_write(UC_ARM_REG_R0,value)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    for name in ('OutdoorCondTempMin','OutdoorCondTempMax'):
        a=f.symbols[name][0]&~1
        f.uc.hook_add(UC_HOOK_CODE,inject,begin=a,end=a)
    return f


def main():
    p=argparse.ArgumentParser();p.add_argument('--old',action='store_true');args=p.parse_args()
    version='12.42' if args.old else '12.43'
    folder='vfd_scale_v1242_20261112' if args.old else 'restart_guard_v1060_v1243_20261112'
    rows=[];hashes={}
    def check(profile,name,observed,expected):
        row=dict(profile=profile,name=name,observed=observed,expected=expected,passed=observed==expected)
        rows.append(row);assert row['passed'],row
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        image=ROOT/'.codex-tmp'/folder/profile/f'PSC316_V{version}_{profile}.axf'
        hashes[profile]=hashlib.sha256(image.read_bytes()).hexdigest()
        for label,ambient,maximum,recovers in (
            ('environment-above10',101,290,True),('condensing-above42',79,421,True),
            ('environment-equal10',100,290,False),('condensing-equal42',79,420,False)):
            f=fixture(image,ambient,maximum);timeline=[]
            for second in range(1,61):
                f.var('Systick_1ms',100000+second*1000);f.var('uc1s',1)
                f.call('BoardFanControl')
                f.call('OutdoorProtectOutputLimit')
                timeline.append(dict(second=second,compressors=[f.var('output',index=i,width=1) for i in (0,1)],
                    fan_commands=[f.p(a) for a in (872,874)],
                    stage=f.var('OutdoorTypeIIStage'),low_off=f.var('OutdoorTypeIILowFanOff'),
                    regulated_stop=f.var('OutdoorFanRegulationStop')))
            if args.old and recovers:
                check(profile,label+'/old-interlock-drop-reproduced',
                    any(s['compressors']!=[1,1] for s in timeline),True)
            else:
                check(profile,label+'/compressors-continuous',
                    all(s['compressors']==[1,1] for s in timeline),True)
                check(profile,label+'/fan-recovery',timeline[-1]['fan_commands'],[0,1] if recovers else [0,0])
                check(profile,label+'/30s-latch',timeline[28]['low_off'],1)
                check(profile,label+'/at30s-latch',timeline[29]['low_off'],0 if recovers else 1)
            rows.append(dict(profile=profile,name=label+'/timeline',passed=True,timeline=timeline))
        if not args.old:
            for label,setup in (('disabled',lambda f:f.p(167,1)),
                ('configuration-invalid',lambda f:f.p(166,4)),
                ('ambient-lockout',lambda f:f.var('AmbientLockout',1))):
                f=fixture(image,79,290);f.var('OutdoorFanRegulationStop',1)
                setup(f);f.call('OutdoorProtectOutputLimit')
                check(profile,label+'/still-cuts-compressors',
                      [f.var('output',index=i,width=1) for i in (0,1)],[0,0])
    name='typeII_recovery_ARM_old_reproduction.json' if args.old else 'typeII_recovery_ARM_results.json'
    dest=ROOT/'测试证据/四项复核_20261112'/name
    checks=[r for r in rows if 'timeline' not in r]
    dest.write_text(json.dumps(dict(total=len(checks),passed=sum(r['passed'] for r in checks),trace_records=len(rows)-len(checks),
        hardware_access=False,temperature_conversion_stubbed=True,AXF_SHA256=hashes,rows=rows),
        ensure_ascii=False,indent=2),encoding='utf8')
    print(len(checks),'typeII recovery ARM checks passed;',len(rows)-len(checks),'trace records')


if __name__=='__main__':main()
