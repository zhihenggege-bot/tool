"""Preserve cooling four stages and the explicitly retained >36C load rule.

Actual ARM regulators, with only condensation conversion replaced by a specified
temperature. This is not a pressure-conversion or terminal-output acceptance.
"""
import json
from test_defrost_lifecycle_arm import Firmware, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_LR

PACKAGE=ROOT/'.codex-tmp/issuefix_v1059_v1241_20261111'
ROWS=[]


def check(profile,name,observed,expected):
    row=dict(profile=profile,name=name,observed=observed,expected=expected,passed=observed==expected)
    ROWS.append(row)
    assert row['passed'],row


def fixture(profile, fan, tmin, tmax=None):
    f=Firmware(PACKAGE/profile/f'PSC316_V12.41_{profile}.axf')
    for a,v in {1:0,107:1,165:1 if fan==3 else 2,166:fan,172:300,173:150,
                176:50,177:5,178:10,179:30,180:30,1422:100}.items(): f.p(a,v)
    def inject(uc,address,size,user):
        value=tmin if address==(f.symbols['OutdoorCondTempMin'][0]&~1) else (tmin if tmax is None else tmax)
        uc.reg_write(UC_ARM_REG_R0,value)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    for name in ('OutdoorCondTempMin','OutdoorCondTempMax'):
        a=f.symbols[name][0]&~1
        f.uc.hook_add(UC_HOOK_CODE,inject,begin=a,end=a)
    return f


def main():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for temp,stage,output in ((299,1,[0,1,0]),(300,1,[0,1,0]),(301,2,[1,0,0]),
            (375,2,[1,0,0]),(376,3,[1,1,0]),(450,3,[1,1,0]),(451,4,[1,1,1])):
            f=fixture(profile,3,temp)
            for ms in range(0,120001,100):
                f.var('Systick_1ms',100000+ms)
                f.var('uc1s',int(ms%1000==0))
                f.call('OutdoorFanUpdateTimers')
                f.call('OutdoorFanTypeII')
            check(profile,f'four-stages/Tc{temp}/stage',f.var('OutdoorTypeIIStage'),stage)
            check(profile,f'four-stages/Tc{temp}/commands',
                [f.p(872),f.p(874),f.var('OutdoorTypeIIFan2High')],output)
        # Stage transition still holds15s. Isolate the target stage from output gates.
        f=fixture(profile,3,301)
        f.var('uc1s',0)
        f.call('OutdoorFanTypeII')
        f.var('uc1s',1)
        for _ in range(14):f.call('OutdoorFanTypeII')
        check(profile,'stage1to2/14s',f.var('OutdoorTypeIIStage'),1)
        f.call('OutdoorFanTypeII')
        check(profile,'stage1to2/15s',f.var('OutdoorTypeIIStage'),2)
        # Original strict comparisons at the low-temperature fan-off thresholds.
        for env,temp,want in ((79,299,1),(80,299,0),(79,300,0)):
            f=fixture(profile,3,temp)
            f.p(1422,env)
            f.var('uc1s',1)
            for _ in range(29):f.call('OutdoorFanTypeII')
            check(profile,f'low-off/{env}/{temp}/29s',f.var('OutdoorTypeIILowFanOff'),0)
            f.call('OutdoorFanTypeII')
            check(profile,f'low-off/{env}/{temp}/30s',f.var('OutdoorTypeIILowFanOff'),want)
        for temp,want in ((339,190),(340,200),(350,200),(360,200),(361,210)):
            f=fixture(profile,4,temp)
            f.p(872,1)
            f.var('OutdoorVfdOn',1)
            f.var('OutdoorVfdSpeed',200)
            f.var('OutdoorFanChangeSeconds',100)
            for second in range(1,31):
                f.var('Systick_1ms',100000+second*1000)
                f.var('uc1s',1)
                f.call('OutdoorFanUpdateTimers')
                f.call('OutdoorFanTypeIII')
            check(profile,f'fixed-vfd/Tc{temp}/retained-boundary',f.var('OutdoorVfdSpeed'),want)
    dest=ROOT/'测试证据/修复回归_20261111/fan_threshold_results.json'
    dest.write_text(json.dumps(dict(total=len(ROWS),passed=sum(r['passed'] for r in ROWS),
        hardware_access=False,temperature_conversion_stubbed=True,rows=ROWS),ensure_ascii=False,indent=2)+'\n','utf8')
    print(len(ROWS),'fan threshold checks passed')


if __name__=='__main__':main()
