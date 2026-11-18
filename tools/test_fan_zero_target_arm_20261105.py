"""V10.52 actual ARM: automatic zero/range fixes and affected manual paths."""
import json,hashlib
from test_defrost_lifecycle_arm import Firmware,ROOT
P=ROOT/'.codex-tmp/fan_zero_target_v1052_v1239_20261105'
checks=[]
def check(label,got,want):
    checks.append({'label':label,'got':got,'expected':want,'passed':got==want})
    assert got==want,(label,got,want)
def board(profile,mode=2):
    f=Firmware(str(P/profile/f'PSC330_V10.52_{profile}.axf'));f.uc.mem_map(0x22000000,0x100000)
    f.call('ParameterInit')
    for a in range(500):f.p(a,f.var('Parameter_def',index=a,width=2))
    for a,v in {1:mode,236:mode,700:4,709:2,329:3,330:2,331:1,335:0,336:0,337:0,338:0,
        381:0,386:0,339:60,340:60,341:30,342:90,1265:1,617:0,131:50,134:50,290:1,291:10}.items():f.p(a,v)
    f.var('Systick_1ms',30000);f.var('UserPump',1);f.var('uc1s',1)
    return f
def main():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for old in (0,70,700,9999):
            f=board(profile);f.p(294,old);f.p(310,old);f.p(344,100)
            for v,want in ((0,0),(1,0),(720,20),(1440,40),(10000,277)):
                f.p(343,v);check(f'{profile} volume{v} legacy{old}',f.call('FanSpecAirSpeedTarget'),want)
            for v in (0,1,100,1500):
                f.p(345,v);check(f'{profile} pressure{v} legacy{old}',f.call('FanSpecAirPressureTarget'),v)
        for mode in (0,1,2):
            for minimum,maximum in ((0,100),(30,90),(60,60),(90,30),(100,0)):
                f=board(profile,mode);f.p(341,minimum);f.p(342,maximum)
                f.p(133,1);f.p(308,1);f.p(345,0);f.p(310,700);f.p(1125,0)
                for _ in range(3):f.call('FanAction')
                low=minimum*10;high=max(minimum,maximum)*10
                check(f'{profile} target zero mode{mode}',f.call('FanSpecDemandTarget'),0)
                demand=f.p(926)
                check(f'{profile} auto range mode{mode} {minimum}/{maximum}',low<=demand<=high,True)
                f.call('IndoorApplyFanValveState',1,1,1,1)
                for fn in ('IndoorEnforceConfiguredOutputDisable','IoOutAction','IndoorEnforceConfiguredOutputDisable'):f.call(fn)
                check(f'{profile} final range mode{mode} {minimum}/{maximum}',f.var('DA',index=7,width=2),demand)
                for volt in (0,50,100):
                    f.p(329,2);f.p(134,volt);f.call('IndoorApplyFanValveState',1,1,1,1)
                    for fn in ('IndoorEnforceConfiguredOutputDisable','IoOutAction','IndoorEnforceConfiguredOutputDisable'):f.call(fn)
                    check(f'{profile} manual mode{mode} range{minimum}/{maximum} volt{volt}',f.var('DA',index=7,width=2),volt*10)
                    check(f'{profile} return unchanged mode{mode}',f.var('DA',index=4,width=2),500)
    report={'hardware_access':False,'checks':checks,'sha256':{profile:hashlib.sha256((P/profile/f'PSC330_V10.52_{profile}.axf').read_bytes()).hexdigest() for profile in ('PRODUCTION','BENCH_ONLY_3S')}}
    (P/'fan_boundary_ARM.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('FAN BOUNDARIES',len(checks),'PASSED',flush=True)
if __name__=='__main__':main()
