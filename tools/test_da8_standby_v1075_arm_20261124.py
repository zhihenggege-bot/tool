"""Execute DA8 production ARM: standby minimum, release and safety priority."""
import hashlib
import json
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware
import build_da8_standby_v1075_20261124 as build

NEW=build.OUT/'PRODUCTION/PSC330_V10.75_PRODUCTION.axf'
OLD=build.OLD/'PSC330_V10.74_PRODUCTION.axf'
checks=[]


def board(settings=None,image=NEW):
    f=Firmware(image);f.uc.mem_map(0x22000000,0x100000);f.call('ParameterInit');f.var('BoardAddressSet',0)
    for a in range(500):f.p(a,f.var('Parameter_def',index=a,width=2))
    f.call('PWMOutProcess')
    for a,v in {1:0,236:0,709:0,247:500,346:200,512:-1,329:0,330:0,331:0,
        334:0,335:0,336:0,337:0,338:0,128:0,127:0,332:0,333:0,315:0}.items():f.p(a,v)
    for a,v in (settings or {}).items():f.p(a,v)
    return f


def ao(f,ch):return f.var('DA',index=ch,width=2)


def scan(f):
    f.call('ColdWaterValveDA8Control');f.call('IndoorEnforceConfiguredOutputDisable')
    f.call('IndoorSyncFinalAOStatus');f.call('PWMOutProcess')
    return [f.p(925),f.p(922),ao(f,8),f.read(0x4000043c,4)]


def check(name,ok,**details):
    checks.append(dict(name=name,passed=bool(ok),**details));assert ok,checks[-1]


def values(expected):return [expected,expected,expected,expected*98//100]


def main():
    report=dict(passed=False,hardware_access=False,checks=checks)
    try:
        for mode in (0,1,2,3,4,5):
            for step in (0,1,2,3,4,5):
                f=board({1:mode,236:mode,709:step})
                for minimum in (0,200,1000):
                    for temp in (-1,0,1):
                        for manual in (0,500,1000):
                            f.p(346,minimum);f.p(512,temp);f.p(247,manual)
                            expected=manual if mode in (0,1) and step==2 else 0
                            if temp<0:expected=max(expected,minimum)
                            result=scan(f)
                            check(f'mode{mode} step{step} min{minimum} temp{temp} manual{manual}',
                                result==values(expected) and f.p(247)==manual,observed=result)
        for step in (0,1,2,3,4,5):
            for name,index in (('IndoorSensorPartialStopFlag',None),('RemoteInterlockStopFlag',None),
                ('SysErrStatus',710),('ModUrgencyStop',1406),('TSysOutTempErr',600),
                ('AntiFreezeErr',602),('FireAlarmX1',None),('ValveLinkX4',None),('LeakProtectX13',None)):
                f=board({709:step})
                if index is None:
                    if name in f.symbols:f.var(name,1)
                    else:
                        aliases={'FireAlarmX1':'X01_En','ValveLinkX4':'X04_En','LeakProtectX13':'X13_En'}
                        f.var(aliases[name],1)
                else:f.p(index,1)
                check(f'step{step} safety{name} keeps DA8 closed',scan(f)==values(0))
        f=board()
        for temp,minimum,expected in ((-1,200,200),(0,200,0),(-1,200,200),(-1,0,0),(-1,1000,1000),(1,1000,0)):
            f.p(512,temp);f.p(346,minimum)
            # Standby UserAction may have returned before the water control function.
            f.call('IndoorEnforceConfiguredOutputDisable');f.call('IndoorSyncFinalAOStatus');f.call('PWMOutProcess')
            observed=[f.p(925),f.p(922),ao(f,8),f.read(0x4000043c,4)]
            check(f'final guard alone releases prior output temp{temp} min{minimum}',observed==values(expected))
        for mode in range(6):
            f=board({1:mode,236:mode,346:200})
            check(f'allmode{mode} requires fresh probe when minimum enabled',f.call('IndoorNtcRequired',2)==1)
            f.p(346,0)
            check(f'allmode{mode} original optional probe when minimum disabled',f.call('IndoorNtcRequired',2)==0)
        for mode in (0,1):
            f=board({1:mode,236:mode,709:2,346:0,600:1,247:500})
            old=board({1:mode,236:mode,709:2,346:0,600:1,247:500},OLD)
            check(f'mode{mode} unused fresh fault with frost disabled preserves manual',scan(f)==scan(old)==values(500))
        for mode in (0,1):
            for manual in (0,100,500,1000):
                for temp in (-1,0,1):
                    old,new=(board({1:mode,236:mode,709:2,247:manual,512:temp},img) for img in (OLD,NEW))
                    check(f'unchanged running mode{mode} target{manual} fresh{temp}',scan(old)==scan(new))
        f=board({709:0,512:-1,247:1000,346:200})
        f.call('ColdWaterValveDA8Control');f.call('IndoorEnforceConfiguredOutputDisable')
        check('standby ignores manual1000 and holds only minimum200',ao(f,8)==200)
        f.p(709,2);check('normal run resumes original manual1000',scan(f)==values(1000))
        f.p(709,3);check('normal shutdown immediately returns to minimum200',scan(f)==values(200))
        for mode,heat_mode,share in ((1,2,1),(0,1,1),(0,1,0)):
            f=board({1:mode,236:mode,709:2,128:heat_mode,127:1,129:share,
                332:1,333:1,738:250,739:250,512:-1,356:-100,357:-200,374:0})
            f.call('PreHeatControl');f.call('HeatControl_UP');f.call('IndoorEnforceConfiguredOutputDisable')
            check(f'electric frost separation mode{mode} heat{heat_mode} share{share}',
                all(ao(f,i)==0 for i in (0,1,9)) and ao(f,8)==200)
        report.update(passed=True,image_sha256=hashlib.sha256(NEW.read_bytes()).hexdigest())
    finally:
        (build.DAY/'standby_ARM_regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print('ARM PASS',len(checks),'checks',flush=True)


if __name__=='__main__':main()
