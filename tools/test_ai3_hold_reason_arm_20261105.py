"""Both V10.51 profiles: limited fixes and affected paths, offline ARM only."""
import json,hashlib,traceback
import test_defrost_lifecycle_arm as arm
import test_indoor_3133_arm as seq
from test_runtime_count_arm_20261105 import statuses
ROOT=arm.ROOT;PACKAGE=ROOT/'.codex-tmp/ai3_hold_reason_v1051_v1239_20261105'
checks=[]
def check(got,want,label):
    checks.append({'label':label,'got':got,'expected':want,'passed':got==want})
    assert got==want,(label,got,want)
def board(profile,mode=0):
    f=arm.Firmware(str(PACKAGE/profile/f'PSC330_V10.51_{profile}.axf'))
    f.uc.mem_map(0x22000000,0x100000);f.call('ParameterInit')
    for a in range(500):f.p(a,f.var('Parameter_def',index=a,width=2))
    for a,v in {1:mode,236:mode,214:3,709:2,700:4,738:250,739:250,
                329:3,330:2,331:1,381:0,386:0,128:2,127:1,332:1,333:0,315:0,512:50}.items():f.p(a,v)
    f.var('Systick_1ms',30000);f.var('X_02',1)
    for a in range(250,258):f.p(a,1)
    return f
def main():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for mode in (0,1,2):
            for fan in (1,2,3):
                for fault in (0,1):
                    f=board(profile,mode);f.p(329,fan);f.p(617,fault)
                    f.call('BoardErrAction')
                    check(f.var('IndoorSensorPartialStopFlag',width=1),int(fan==3 and fault and mode!=2),
                          f'{profile} AI3 partial-stop mode{mode} fan{fan} fault{fault}')
                    check(f.p(710),0,f'{profile} AI3 preserves fan whole-unit permission')
                    if fan==3 and fault:
                        f.var('UserPump',1);f.p(339,60);f.p(340,60);f.p(341,30);f.p(342,90)
                        f.call('FanAction')
                        check(f.p(926),600,f'{profile} AI3 fan fallback still600 mode{mode}')
        for mode in (0,1):
            f=board(profile,mode)
            for a,v in {128:2,127:1,129:1,332:1,333:1,374:0,356:0,357:-50,
                        346:300,512:-25,738:124,739:250,125:1,126:1,
                        248:1,334:1,168:1,169:1,162:500,501:300}.items():f.p(a,v)
            f.call('HeatControl_UP');f.call('PreHeatControl');f.call('HumidtCtrl')
            f.call('IndoorApplyFanValveState',1,1,1,1)
            check(int(f.p(890)>0 and (mode==0 or f.p(891)>0) and f.p(892)>0),1,
                  f'{profile} AI3 branch fixture establishes all thermal loads mode{mode}')
            f.p(617,1);f.call('BoardErrAction')
            check(f.var('IndoorSensorPartialStopFlag',width=1),1,f'{profile} AI3 branch selected')
            # Execute the actual functions in the existing partial-stop branch,
            # then final writers. Scheduling/ADC propagation is a board gap.
            for fn in ('IndoorClearOutdoorRunCommands','IndoorStopHeatPreheatLoads',
                       'IndoorStopHumidifier','FanAction','IndoorFanValveOutputs',
                       'IndoorEnforceConfiguredOutputDisable','IoOutAction','IndoorEnforceConfiguredOutputDisable'):f.call(fn)
            check([f.p(890),f.p(891),f.p(892)]+[f.var('DA',index=i,width=2) for i in (0,1,2,9)],
                  [0]*7,f'{profile} AI3 clears heat/preheat/humid and winter minimum stays off mode{mode}')
            check([f.var('output',index=i,width=1) for i in (3,6,8)],[1,1,1],
                  f'{profile} AI3 preserves supply/return/exhaust relays mode{mode}')
        for actual in range(5):
            for reheat in (0,1):
                for mode in (0,1):
                    f=board(profile,mode);f.p(127,reheat);f.p(332,reheat)
                    statuses(f,[2]*actual+[0]*(4-actual));f.var('uc100ms',1)
                    for _ in range(150):f.call('SysNergryAction_PID')
                    check([f.p(881),f.p(118),f.p(119),f.p(707)],[actual,actual,actual,0],
                          f'{profile} Z0 actual{actual} reheat{reheat} mode{mode}')
        for fn in ('SysNergryAction','SysNergryAction_PID'):
            for auto in (0,1):
                for fresh,inverter in ((0,0),(1,1)):
                    f=board(profile);f.p(315,1);f.p(327,fresh);f.p(38,inverter);f.p(320,auto)
                    f.call('IndoorAutoCoolHeatSwitchAction');f.call(fn)
                    check([f.p(893),f.p(881),f.p(118),f.p(707)],[6 if auto else 7,0,0,4],
                          f'{profile} {fn} auto{auto} invalid ambient fresh{fresh} inverter{inverter}')
                    f.p(320,1-auto);f.call('IndoorAutoCoolHeatSwitchAction');f.call(fn)
                    check(f.p(893),7 if auto else 6,f'{profile} diagnostic priority follows enable, no stale reason')
    # Existing full production startup/shutdown and special-mode assertions.
    arm.IN=str((PACKAGE/'PRODUCTION/PSC330_V10.51_PRODUCTION.axf').relative_to(ROOT))
    seq.main()
    report={'hardware_access':False,'scope':'actual V10.51 production and BENCH machine code, offline',
            'checks':checks,'sequence_checks_passed':seq.passed,
            'sha256':{str(p.relative_to(PACKAGE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in PACKAGE.glob('*/*.axf')}}
    (PACKAGE/'targeted_ARM.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('TARGETED',len(checks),'SEQUENCE',seq.passed,'ALL PASSED',flush=True)
if __name__=='__main__':main()
