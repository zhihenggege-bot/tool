"""Check actual ARM ambient-permission counters without an on-demand request."""
from pathlib import Path
import json
from test_defrost_lifecycle_arm import Firmware

R=Path(__file__).resolve().parents[1]
AXF=R/'.codex-tmp/vfd_unload_min30_v1063_v1246_20261117/PRODUCTION/PSC316_V12.46_PRODUCTION.axf'
rows=[]


def fixture(mode=0,kind=0,temp=250):
    f=Firmware(str(AXF));f.call('ParameterInit')
    for a,v in {1:mode,165:kind,170:150,171:180,1422:temp,1401:0,1402:0}.items():f.p(a,v)
    f.var('uc1s',0);f.call('AmbientProtectAction')
    return f


def tick(f,n):
    f.var('uc1s',1)
    for _ in range(n):f.call('AmbientProtectAction')


def check(label,condition):
    rows.append(dict(label=label,passed=bool(condition)));assert condition,label


for mode,kind,temp in ((0,0,250),(0,1,100),(0,2,100),(1,0,100)):
    f=fixture(mode,kind,temp)
    tick(f,299);check(f'{mode}/{kind}/no-demand-299s-still-locked',f.var('AmbientLockout')==1)
    tick(f,1);check(f'{mode}/{kind}/no-demand-300s-permitted',f.var('AmbientLockout')==0)
    tick(f,30);check(f'{mode}/{kind}/no-demand-does-not-reset-count',f.var('AmbientLockout')==0)
    check(f'{mode}/{kind}/no-request-or-outputs-injected',f.p(1401)==0 and f.p(1402)==0)

f=fixture();tick(f,200);f.p(1422,150);tick(f,1)
check('cool/start-condition-fails-count-reset',f.var('LowRecoverCount')==0 and f.var('AmbientLockout')==1)
f.p(1422,250);tick(f,299);check('cool/recovery-needs-new-300s',f.var('AmbientLockout')==1)
tick(f,1);check('cool/recovered-after-new-300s',f.var('AmbientLockout')==0)

f=fixture();tick(f,300);f.p(1,1);f.p(1422,100);f.var('uc1s',0);f.call('AmbientProtectAction')
check('mode-change-clears-previous-permission',f.var('AmbientLockout')==1 and f.var('HighRecoverCount')==0)
tick(f,299);check('new-mode-299s-locked',f.var('AmbientLockout')==1)
tick(f,1);check('new-mode-300s-permitted',f.var('AmbientLockout')==0)

f=fixture();tick(f,300);f.p(165,1);f.var('uc1s',0);f.call('AmbientProtectAction')
check('unit-type-change-resets',f.var('AmbientLockout')==1 and f.var('LowRecoverCount')==0)
f=fixture();tick(f,200);f.var('SensorStatus',1,index=6,width=1);tick(f,1)
check('ambient-sensor-fault-resets-counts',f.var('HighRecoverCount')==0 and f.var('LowRecoverCount')==0 and f.var('AmbientLockout')==1)

p=R/'测试证据/切换正式时序_20261118/ambient_ARM.json'
p.write_text(json.dumps(dict(passed=True,total=len(rows),hardware_access=False,rows=rows),ensure_ascii=False,indent=2),'utf8')
print(len(rows),'ARM ambient checks passed')
