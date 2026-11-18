"""Actual ARM ramps with interleaved non-second scans, old/new comparison."""
import itertools
import json
from test_defrost_lifecycle_arm import Firmware, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_LR

O=ROOT/'.codex-tmp/vfd_unload_v1063_v1245_20261117'
OLD=ROOT/'.codex-tmp/manual_gate_v1063_v1244_20261113'


def fixture(path,pair,speed=400,temp=330,step=10,fixed=0):
    f=Firmware(path)
    for a,v in {1:0,107:1,165:pair[0],166:pair[1],176:40,177:10,178:step,
                179:30,180:30,1400:0,1403:0}.items():f.p(a,v)
    for name,value in (('OutdoorVfdOn',1),('OutdoorFixedOn',fixed),('OutdoorVfdSpeed',speed),
                       ('OutdoorVfdUnloadCount',30),('OutdoorFanChangeSeconds',100),('Systick_1ms',100000)):
        f.var(name,value)
    for i in range(2):
        f.var('OutdoorFanRunTickValid',1,i,1);f.var('OutdoorFanRunTick',0,i,4)
        f.var('OutdoorFanStopTickValid',1,i,1);f.var('OutdoorFanStopTick',0,i,4)
    def temperature(uc,address,size,data):
        uc.reg_write(UC_ARM_REG_R0,temp)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    addr=f.symbols['OutdoorCondTempMax'][0]&~1
    f.uc.hook_add(UC_HOOK_CODE,temperature,begin=addr,end=addr)
    return f


def state(f):
    return [f.var(n) for n in ('OutdoorVfdOn','OutdoorFixedOn','OutdoorVfdSpeed')]+[f.p(n) for n in (872,874,1468)]


def main():
    results=[]
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        path=O/profile/f'PSC316_V12.45_{profile}.axf'
        oldpath=OLD/profile/f'PSC316_V12.44_{profile}.axf'
        old_reproductions=[];ramps=[]
        for unit,step,initial in itertools.product((1,2),(1,10,20),(300,400)):
            f=fixture(path,(unit,2),initial,step=step)
            f.var('uc1s',0);f.call('OutdoorFanTypeIII')
            assert f.var('OutdoorVfdSpeed')==initial and f.var('OutdoorVfdOn')==1
            history=[]
            for second in range(1,305):
                before=f.var('OutdoorVfdSpeed');f.var('uc1s',1);f.call('OutdoorFanTypeIII')
                after=f.var('OutdoorVfdSpeed')
                if before>100:assert after==max(100,before-step)
                history.append(state(f));f.var('uc1s',0)
                for scan in range(5):
                    prior=f.var('OutdoorVfdSpeed');f.call('OutdoorFanTypeIII')
                    if prior>100:assert f.var('OutdoorVfdOn')==1 and f.var('OutdoorVfdSpeed')==prior
                if not f.var('OutdoorVfdOn'):break
            assert not f.var('OutdoorVfdOn') and any(s[2]==100 for s in history)
            ramps.append(dict(unit_type=unit,step10=step,initial_speed10=initial,seconds=second,
                              reached_minimum=True,off=True,nonsecond_hold_passed=True))
        for unit in (1,2):
            old=fixture(oldpath,(unit,2));old.var('uc1s',1);old.call('OutdoorFanTypeIII')
            first=state(old);old.var('uc1s',0);old.call('OutdoorFanTypeIII')
            assert first[2]==390 and old.var('OutdoorVfdOn')==0
            old_reproductions.append(dict(unit_type=unit,after_tick=first,after_nonsecond=state(old)))
            f=fixture(path,(unit,2),100);f.var('OutdoorFanRunTick',90000,0,4)
            f.var('uc1s',0);f.call('OutdoorFanTypeIII');assert f.var('OutdoorVfdOn')==1
            f.var('Systick_1ms',120000);f.call('OutdoorFanTypeIII');assert f.var('OutdoorVfdOn')==0
            f=fixture(path,(unit,2),100);f.var('OutdoorFanChangeSeconds',0)
            f.var('uc1s',0);f.call('OutdoorFanTypeIII');assert f.var('OutdoorVfdOn')==1
            f=fixture(path,(unit,2),0,temp=350);f.var('OutdoorVfdOn',0)
            f.var('OutdoorFanStopTick',90000,0,4);f.var('uc1s',0)
            f.call('OutdoorFanTypeIII');assert f.var('OutdoorVfdOn')==0
            f.var('Systick_1ms',120000);f.call('OutdoorFanTypeIII');assert f.var('OutdoorVfdOn')==1
        equal=0
        # All stable/load single-VFD paths and fixed+VFD paths stay equal.
        for pair,temp,speed,tick in itertools.product(((1,2),(2,2),(2,4)),(330,350,370,460),(100,250,400),(0,1)):
            if pair[1]==2 and temp==330:continue
            for fixed in ((0,1) if pair[1]==4 else (0,)):
                old=fixture(oldpath,pair,speed,temp,fixed=fixed);new=fixture(path,pair,speed,temp,fixed=fixed)
                for f in (old,new):f.var('uc1s',tick);f.call('OutdoorFanTypeIII')
                assert state(old)==state(new),(profile,pair,temp,speed,tick,fixed,state(old),state(new))
                equal+=1
        row=dict(profile=profile,old_defect_reproduced=old_reproductions,ramps=ramps,
                 unchanged_fan_branch_comparisons=equal,minrun_minstop_action_gates_passed=True,passed=True)
        results.append(row);print('VFD ARM PASS',profile,'ramps',len(ramps),'equal',equal,flush=True)
    (O/'unload_ARM_regression.json').write_text(json.dumps(dict(scope='Actual compiled ARM, initialized local fixtures; no board access',results=results),indent=2),encoding='utf8')


if __name__=='__main__':main()
