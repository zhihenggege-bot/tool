"""Lifecycle/selection edge coverage in current linked code, emulated time only."""
import json
import traceback
import test_defrost_lifecycle_arm as life
from remaining529_offline_matrix_20261105 import init,ck,checks,cases,D,P

def lifecycle():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        f=init(profile,1)
        f.p(709,3)
        f.field(False,1,'CanDefrost',value=7)
        f.field(True,1,'CompControl',0,1)
        f.call('CompNormalStopAction')
        ck('T16-003',profile+' recovery stopped compressor request retires',f.field(True,1,'CompControl',0),0)
        ck('T16-003',profile+' recovery still blocks complete outdoor stop',f.call('IndoorOutdoorStopped'),0)
        f.field(False,1,'CanDefrost',value=0)
        ck('T16-003',profile+' completed lifecycle releases outdoor stop gate',f.call('IndoorOutdoorStopped'),1)
        for phase in (7,8):
            f=init(profile,1)
            f.field(False,1,'CanDefrost',value=phase)
            f.field(False,1,'CompStatus',0,3)
            f.field(True,1,'CompControl',0,1)
            for target in (0,8):
                f.p(881,target)
                ck('T16-004',profile+f' phase{phase} target{target} no unload in defrost',f.call('CompCanUnload',1,0),0)
                ck('T16-004',profile+f' phase{phase} target{target} no new load in defrost',f.call('CompCanLoad',1,1),0)
            for ch in (0,1,2,9):f.var('DA',700,ch,2)
            for ch in (0,1,2,3,4,6,7,8,9,10,11,12,13,14,15):f.var('output',1,ch,1)
            f.p(710,1)
            f.call('IndoorEmergencyStopLoads')
            ck('T16-005',profile+f' phase{phase} emergency clears thermal/fan DOs',
                [f.var('output',index=ch,width=1) for ch in (0,1,2,3,4,6,7,8,9,10,11,12,13,14,15)],[0]*15)
            ck('T16-005',profile+f' phase{phase} emergency clears AOs',
                [f.var('DA',index=ch,width=2) for ch in (0,1,2,9)],[0]*4)
            ck('T16-005',profile+f' phase{phase} emergency clears outdoor requests',
                [f.field(True,m,'CompControl',c) for m in range(1,5) for c in range(2)],[0]*8)
        life.OUT=str(P/profile/f'PSC316_V12.39_{profile}.axf')
        o=life.outdoor()
        o.var('X_00',1)
        o.var('X_02',1)
        o.call('DefrostProcess')
        expected=5 if profile=='BENCH_ONLY_3S' else 60
        life.tick(o,expected-1)
        ck('T16-008',profile+' recovery one tick before deadline',o.p(1420),7)
        life.tick(o,1)
        ck('T16-008',profile+' recovery exact deadline clears',o.p(1420),0)
        f=init(profile,1)
        for a,v in {128:1,127:1,129:1,332:1,365:1,372:350,10:500,12:500}.items():f.p(a,v)
        f.field(False,1,'CanDefrost',value=7)
        f.call('HeatControl_UP')
        ck('T16-008',profile+' recovery auxiliary full',f.p(890),1000)
        # The normal EEV task bridges new setting [372] into the legacy
        # runtime parameter before AutoAction. Reproduce that task prefix.
        f.call('EEVSpecParamBridge')
        ptr=0x20060000
        f.call('EEVSpecAutoAction',0,ptr,ptr+4,ptr+8,ptr+12)
        ck('T16-008',profile+' recovery indoor EEV holds defrost opening',f.p(1145),350)

def configuration():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        f=init(profile,1)
        for value in (-1,0,1,2,3):
            ck('T07-015',profile+f' exhaust selector{value} has no AO enum',f.call('ParamCanWriteFromHMI',331,value),int(value in (0,1)))
        f.p(336,0)
        f.p(337,0)
        for supply,returning,exhaust in ((1,1,1),(2,2,1),(3,2,1),(3,0,0)):
            for a,v in {329:supply,330:returning,331:exhaust,134:50,131:40,926:600,341:30,342:90}.items():f.p(a,v)
            f.call('IndoorApplyFanValveState',1,1,1,1)
            f.call('IndoorEnforceConfiguredOutputDisable')
            ck('T07-085',profile+f' configuration{supply}/{returning}/{exhaust} fan DO enable',
                [f.var('output',index=ch,width=1) for ch in (3,6,8)],[1,int(returning!=0),exhaust])
            ck('T07-085',profile+' return manual AO is configured or zero',f.var('DA',index=4,width=2),400 if returning==2 else 0)
            ck('T07-085',profile+' supply configured AO route',f.var('DA',index=7,width=2),0 if supply==1 else 500 if supply==2 else 600)
            f.call('IndoorApplyFanValveState',0,0,0,0)
            ck('T07-085',profile+' stopped configuration clears both fan AOs',[f.var('DA',index=c,width=2) for c in (4,7)],[0,0])
        f=init(profile,1)
        f.p(738,124)
        f.p(739,250)
        f.p(333,0)
        for kind in (2,3,4,5,0):
            f.p(128,kind)
            for _ in range(12):f.call('HeatControl_UP')
            groups=[f.var('output',index=i,width=1) for i in (0,1,2)]
            analog=f.var('DA',index=0,width=2)
            want={2:([0,0,0],1000),3:([1,1,0],0),4:([1,1,1],0),5:([1,1,0],1000),0:([0,0,0],0)}[kind]
            ck('T07-086',profile+f' selected heat kind{kind} replaces prior AO/DO route',[groups,analog],list(want))

def main():
    errors=[]
    for fn in (lifecycle,configuration):
        try:fn()
        except Exception:
            errors.append({'function':fn.__name__,'traceback':traceback.format_exc()})
            traceback.print_exc()
    (D/'remaining529_lifecycle_configuration_ARM.json').write_text(json.dumps(
        {'hardware_access':False,'time_is_simulated':True,'cases':cases,'checks':checks,'errors':errors,
         'limits':'Lifecycle helpers and output routing only; no board transport, NVRAM, GUI, terminals or real thermal process.'},
        ensure_ascii=False,indent=2),'utf8')
    print('COMPLETE',len(cases),len(checks),'mismatches',sum(not c['passed'] for c in checks),'errors',len(errors),flush=True)

if __name__=='__main__':main()
