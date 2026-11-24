"""Execute production ARM for DA8 manual-only and electric frost separation."""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/"tools"))
from test_defrost_lifecycle_arm import Firmware
ROOT=Path.cwd()
OUT=ROOT/".codex-tmp/da8_water_valve_v1074_20261124"
OLD=ROOT/".codex-tmp/cooling_ambient_v1073_v1256_20261123/PRODUCTION/PSC330_V10.73_PRODUCTION.axf"
NEW=OUT/"PRODUCTION/PSC330_V10.74_PRODUCTION.axf"
checks=[]

def board(settings=None,image=NEW):
    f=Firmware(image)
    f.uc.mem_map(0x22000000,0x100000)
    f.call("ParameterInit")
    f.var("BoardAddressSet",0)
    for a in range(500):
        f.p(a,f.var("Parameter_def",index=a,width=2))
    f.call("PWMOutProcess") # Normal boot-time driver initialization precedes output requests.
    for a,v in {1:1,236:1,709:2,128:2,127:1,129:1,332:1,333:1,346:300,
                738:250,739:250,512:-10,513:100,356:-20,357:-50,412:5,
                329:1,330:0,331:0,334:0,335:0,336:0,337:0,338:0}.items():
        f.p(a,v)
    for a,v in (settings or {}).items():
        f.p(a,v)
    return f

def ao(f,ch):
    return f.var("DA",index=ch,width=2)

def water_scan(f):
    f.call("ColdWaterValveDA8Control")
    f.call("IndoorEnforceConfiguredOutputDisable")
    f.call("IndoorSyncFinalAOStatus")
    f.call("PWMOutProcess")
    return [f.p(925),ao(f,8),f.p(922),f.read(0x4000043c,4)]

def check(name,ok,**details):
    checks.append(dict(name=name,passed=bool(ok),**details))
    assert ok,checks[-1]

try:
    f=board()
    check("manual mode fixed range/default",all(f.var(n,index=245,width=2)==1 for n in ("Parameter_min","Parameter_max","Parameter_def")))
    check("manual opening range/default",[f.var(n,index=247,width=2) for n in ("Parameter_min","Parameter_max","Parameter_def")]==[0,1000,500])
    check("retired automatic helpers removed",all(n not in f.symbols for n in ("PreUpORDown","EEVCheck")))
    for mode in (0,1):
        f=board({1:mode,236:mode})
        for legacy in (0,1):
            for minimum in (0,200,1000):
                for fresh in (-1,0,1):
                    for target in (-1,0,100,500,1000,2000):
                        f.p(245,legacy)
                        f.p(346,minimum)
                        f.p(512,fresh)
                        f.p(247,target)
                        clamped=max(0,min(target,1000))
                        expected=max(clamped,minimum) if fresh<0 else clamped
                        result=water_scan(f)
                        check(f"mode{mode} old245={legacy} min{minimum} fresh{fresh} target{target}",
                              result==[expected,expected,expected,expected*98//100] and f.p(245)==1,
                              observed=result)
    for step in (0,1,3,4,5):
        f=board({709:step,247:700})
        result=water_scan(f)
        check(f"step{step} water remains off",result==[0,0,0,0],observed=result)
    for mode in (2,3,4,5):
        f=board({1:mode,236:mode,247:700})
        result=water_scan(f)
        check(f"nonclimate mode{mode} water off",result==[0,0,0,0])
    for var,value in (("IndoorSensorPartialStopFlag",1),("RemoteInterlockStopFlag",1)):
        f=board({247:700})
        f.var(var,value)
        check(var+" blocks manual and minimum",water_scan(f)==[0,0,0,0])
    for address in (710,1406):
        f=board({247:700,address:1})
        check(f"inhibit{address} blocks manual and minimum",water_scan(f)==[0,0,0,0])
    f=board({247:0,346:200,512:-1})
    water_scan(f)
    f.p(512,0)
    check("warming to exactly0 releases minimum without losing manual target",water_scan(f)==[0,0,0,0] and f.p(247)==0)
    f=board({247:300,346:0,245:0})
    f.var("uc100ms",1)
    f.var("uc1s",1)
    for tick in range(120):
        f.p(738,100 if tick%2 else 400)
        f.p(246,1000)
        for address in range(403,411):
            f.p(address,0)
        result=water_scan(f)
        assert result==[300,300,300,294],(tick,result)
    check("temperature/trend/retired parameters cannot alter manual output",True)
    for mode,heat_mode,share,ch in ((1,2,1,0),(0,1,1,0),(0,1,0,9)):
        f=board({1:mode,236:mode,128:heat_mode,129:share})
        f.call("PreHeatControl")
        f.call("HeatControl_UP")
        f.call("IndoorEnforceConfiguredOutputDisable")
        check(f"electric channel{ch} and preheat no cold floor",ao(f,ch)==0 and ao(f,1)==0 and f.p(890)==f.p(891)==0)
    for mode in (0,1):
        for share in (0,1):
            for temperature,minimum in ((-10,0),(0,300),(1,300),(100,300)):
                settings={1:mode,236:mode,129:share,512:temperature,346:minimum}
                old,new=(board(settings,image) for image in (OLD,NEW))
                for f in (old,new):
                    f.var("uc100ms",1)
                for tick in range(150):
                    if tick==100:
                        old.p(738,230)
                        new.p(738,230)
                    for f in (old,new):
                        for fn in ("PreHeatControl","HeatControl_UP","IndoorEnforceConfiguredOutputDisable"):
                            f.call(fn)
                    assert [ao(old,i) for i in (0,1,9)]==[ao(new,i) for i in (0,1,9)]
                    assert [old.p(i) for i in (890,891)]==[new.p(i) for i in (890,891)]
                check(f"ordinary electric PID preserved mode{mode} share{share} fresh{temperature} min{minimum}",True)
    for mode in (0,1):
        f=board({1:mode,236:mode,315:0,333:0,377:2,346:0})
        check(f"unused fresh probe optional mode{mode}",f.call("IndoorNtcRequired",2)==0)
        f.p(346,200)
        check(f"frost minimum requires fresh probe mode{mode}",f.call("IndoorNtcRequired",2)==1)
        f.p(1,2)
        f.p(236,2)
        check("ventilation does not add frost probe requirement",f.call("IndoorNtcRequired",2)==0)
    f=board({1:0,236:0,602:1,214:1})
    f.call("ColdWaterValveDA8Control")
    before=ao(f,8)
    f.call("BoardErrAction")
    f.call("IndoorEnforceConfiguredOutputDisable")
    check("existing antifreeze alarm emergency keeps final priority",before==1000 and ao(f,8)==0 and f.p(709)==0,
          before_error=before,after_error=ao(f,8))
    f=board({245:0,709:0})
    f.call("SysDataPross")
    check("old EEPROM automatic value normalized while stopped",f.p(245)==1)
    report=dict(passed=True,hardware_access=False,checks=checks,
                image_sha256=hashlib.sha256(NEW.read_bytes()).hexdigest(),
                scope="Manual water setpoint and low-temperature floor, final software PWM, protections and adjacent electrical PID preservation")
finally:
    if "report" not in globals():
        report=dict(passed=False,hardware_access=False,checks=checks)
    (OUT/"manual_ARM_regression.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),"utf8")
print("ARM PASS",len(checks),flush=True)
