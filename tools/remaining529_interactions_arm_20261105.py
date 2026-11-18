"""Two simultaneous protection inputs and communication recovery in linked ARM.

No board access, no physical contacts, no wall-clock qualification.
"""
import json, traceback
from remaining529_offline_matrix_20261105 import init,ck,checks,cases,D
from remaining529_protection_arm_20261105 import reset

def multiple_faults():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        f=init(profile)
        f.p(510,250); f.var('uc1s',1)
        f.var('X01_En',1); f.var('X_05',1)
        for _ in range(15): f.call('BoardErrAction')
        ck('T05-041',profile+' fire and filter both latched',[f.p(605),f.p(909),f.p(710)],[1,1,1])
        f.var('X_05',0); reset(f); f.call('BoardErrAction')
        ck('T05-041',profile+' filter removed/reset cannot release active fire',[f.p(605),f.p(909),f.p(710)],[1,0,1])
        f.var('X01_En',0);f.call('BoardErrAction')
        ck('T05-041',profile+' fire input removal retains its latch',f.p(605),1)
        reset(f);f.call('BoardErrAction')
        ck('T05-041',profile+' both healthy/reset releases emergency',f.p(710),0)
        f=init(profile)
        f.p(510,250);f.p(912,1);f.p(125,1)
        f.var('SensorStatus',1,3,1);f.var('SensorErr',1,3,1)
        f.call('SensorErrAction');f.call('BoardErrAction')
        ck('T05-042',profile+' pressure plus AI3 partial stop both present',
           [f.p(912),f.p(710),f.var('IndoorSensorPartialStopFlag',width=1)],[1,1,1])
        reset(f);f.call('SensorErrAction');f.call('BoardErrAction')
        # Raw sensor invalidity must requalify its original diagnostic delay;
        # do not infer immediate relatch from the reset function alone.
        f.var('uc100ms',1)
        for _ in range((f.p(25)+3)*10):f.call('SensorErrAction')
        f.call('BoardErrAction')
        ck('T05-042',profile+' pressure reset cannot mask continuing AI3 fault',
           [f.p(912),f.var('IndoorSensorPartialStopFlag',width=1)],[0,1])
        f.var('SensorStatus',0,3,1);reset(f);f.call('SensorErrAction');f.call('BoardErrAction')
        ck('T05-042',profile+' AI3 healthy/reset releases partial stop',f.var('IndoorSensorPartialStopFlag',width=1),0)
        f=init(profile,1)
        f.p(510,250);f.var('X06_En',1);f.var('X_02',0);f.var('uc100ms',1)
        for _ in range(30):f.call('BoardErrAction')
        ck('T05-043',profile+' electrical heat fault and remote stop coexist',
           [f.p(966),f.var('RemoteInterlockStopFlag',width=1)],[1,1])
        f.var('X_02',1);f.call('BoardErrAction')
        ck('T05-043',profile+' remote return cannot reset active heat fault',
           [f.p(966),f.var('RemoteInterlockStopFlag',width=1)],[1,0])
        reset(f);f.call('BoardErrAction')
        ck('T05-043',profile+' active heat fault rejects manual reset',f.p(966),1)
        f.var('X06_En',0);f.call('BoardErrAction')
        ck('T05-043',profile+' heat removal alone retains latch',f.p(966),1)
        reset(f);f.call('BoardErrAction')
        ck('T05-043',profile+' healthy heat reset clears latch',f.p(966),0)

def communications():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        f=init(profile,1);f.p(510,250)
        for m in (1,2):
            for c in range(2):
                f.field(True,m,'CompControl',c,1)
                f.field(False,m,'CompStatus',c,3)
        f.var('UnitCommErr',1,1,2)
        f.call('CompNormalStopAction')
        ck('T10-025',profile+' silent unit requests isolated',
           [f.field(True,1,'CompControl',c) for c in range(2)],[0,0])
        ck('T10-025',profile+' healthy neighbor keeps feedback',
           [f.field(False,2,'CompStatus',c) for c in range(2)],[3,3])
        f.var('UnitCommErr',1,2,2);f.call('CompNormalStopAction')
        ck('T10-026',profile+' both offline cannot keep either request',
           [f.field(True,m,'CompControl',c) for m in (1,2) for c in range(2)],[0]*4)
        f.var('UnitCommErr',0,1,2)
        for c in range(2):f.field(False,1,'CompStatus',c,0)
        f.call('CompLoading')
        ck('T10-026',profile+' recovered unit eligible and silent unit blocked',
           [f.field(True,m,'CompControl',c) for m in (1,2) for c in range(2)],[1,0,0,0])
        f.p(709,3)
        f.call('CompNormalStopAction')
        ck('T10-027',profile+' immediate normal stop cancels recovered unconfirmed start',
           [f.field(True,m,'CompControl',c) for m in (1,2) for c in range(2)],[0]*4)

def main():
    errors=[]
    for fn in (multiple_faults,communications):
        try:fn()
        except Exception:
            errors.append({'function':fn.__name__,'traceback':traceback.format_exc()});traceback.print_exc()
    (D/'remaining529_interactions_ARM.json').write_text(json.dumps(
        {'hardware_access':False,'time_is_simulated':True,'cases':cases,'checks':checks,'errors':errors,
         'limits':'Function-level simulated fault and online flags; no actual disconnect/reconnect or physical inputs.'},
        ensure_ascii=False,indent=2),'utf8')
    print('COMPLETE',len(cases),len(checks),'mismatches',sum(not c['passed'] for c in checks),'errors',len(errors),flush=True)

if __name__=='__main__':main()
