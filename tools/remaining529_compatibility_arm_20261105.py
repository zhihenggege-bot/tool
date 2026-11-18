"""Current linked-image compatibility probes; no board or physical clock access."""
import json
import traceback
from remaining529_offline_matrix_20261105 import init,ck,checks,cases,D
from remaining529_protection_arm_20261105 import reset

def compatibility():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for cid,ch,flag,fan in (('T05-037','X12_En',958,6),('T05-038','X11_En',956,8)):
            for fanmode in (1,2):
                f=init(profile)
                f.p(330,fanmode)
                f.p(331,1)
                f.var('output',1,fan,1)
                f.var('DA',600,4,2)
                f.var(ch,1)
                f.call('BoardErrAction')
                ck(cid,profile+f' fanmode{fanmode} running overload latch',f.p(flag),1)
                ck(cid,profile+' overload requests emergency stop',f.p(710),1)
                reset(f)
                f.call('BoardErrAction')
                ck(cid,profile+' active overload cannot clear latch',f.p(flag),1)
                f.var(ch,0)
                f.call('BoardErrAction')
                ck(cid,profile+' removal without reset stays latched',f.p(flag),1)
                reset(f)
                f.call('BoardErrAction')
                ck(cid,profile+' healthy reset clears latch',f.p(flag),0)
        f=init(profile)
        f.var('X13_En',1)
        f.call('BoardErrAction')
        ck('T05-039',profile+' leak emergency classification',f.p(710),1)
        f.var('X13_En',0)
        f.call('BoardErrAction')
        ck('T05-039',profile+' leak latch retained',f.p(710),1)
        reset(f)
        f.call('BoardErrAction')
        ck('T05-039',profile+' healthy leak reset',f.p(710),0)
        f=init(profile)
        f.var('DA',600,2,2)
        f.var('DA',700,0,2)
        f.var('output',1,11,1)
        f.var('X10_En',1)
        f.call('BoardErrAction')
        ck('T05-040',profile+' humidifier fault cuts humid AO/DO',
            [f.var('DA',index=2,width=2),f.var('output',index=11,width=1)],[0,0])
        ck('T05-040',profile+' humidifier fault retains main heat',f.var('DA',index=0,width=2),700)
        f.var('X10_En',0)
        f.call('BoardErrAction')
        ck('T05-040',profile+' humidifier latch retained',f.p(910),1)
        reset(f)
        f.call('BoardErrAction')
        ck('T05-040',profile+' healthy humidifier reset',f.p(910),0)

def winter_accepted_behavior():
    # No independent steam/water selection is asserted here. Current electric
    # minimum behavior was explicitly accepted by the user; it is an observation
    # against that decision, not an assertion that the original spec says this.
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for owner,cid,ch in (('Heat','T06-001',0),('Preheat','T06-004',1)):
            f=init(profile,1)
            f.p(346,200)
            for temp in (1,0,-1,-10,1):
                f.p(512,temp)
                f.var('Indoor'+owner+'AnalogMode',1)
                f.var('Indoor'+owner+'AnalogDemand',0)
                f.call('IndoorApplyHeatAnalogOutputs')
                f.call('IndoorEnforceWinterValveMinimum')
                ck(cid,profile+f' accepted electric minimum fresh{temp}',
                    f.var('DA',index=ch,width=2),200 if temp<0 else 0)
            for step in (0,3,4):
                f.p(709,step)
                f.p(512,-10)
                f.var('Indoor'+owner+'AnalogDemand',0)
                f.call('IndoorApplyHeatAnalogOutputs')
                f.call('IndoorEnforceWinterValveMinimum')
                ck(cid,profile+f' no winter re-energize stopped step{step}',f.var('DA',index=ch,width=2),0)

def switch_ambiguity():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        f=init(profile)
        for a,v in {127:0,332:0,125:0,126:0,320:1,322:60,315:0,
                    738:250,739:250,119:0,890:0}.items():f.p(a,v)
        f.var('uc1s',1)
        for _ in range(65):f.call('IndoorAutoCoolHeatSwitchAction')
        ck('T11-103',profile+' full stop65s warm has not switched',f.p(236),0)
        f.p(738,239)
        for _ in range(59):f.call('IndoorAutoCoolHeatSwitchAction')
        ck('T11-103',profile+' newly low needs another59s',f.p(236),0)
        f.call('IndoorAutoCoolHeatSwitchAction')
        ck('T11-103',profile+' actual implementation jointly qualifies60s',f.p(236),1)

def coil_interruptions():
    temps=(515,516,514,517,520,521,522,523)
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for circuit,reg in enumerate(temps):
            f=init(profile)
            for a in temps:f.p(a,100)
            for a,v in {110:5,111:-20,112:50,114:2,510:250}.items():f.p(a,v)
            f.var('uc1s',1)
            f.p(reg,-21)
            for _ in range(299):f.call('BoardErrAction')
            f.p(reg,-20)
            f.call('BoardErrAction')
            f.p(reg,-21)
            for _ in range(299):f.call('BoardErrAction')
            ck('T15-009',profile+f' circuit{circuit} interrupted low299 restarts timer',f.p(640+circuit),0)
            f.call('BoardErrAction')
            ck('T15-009',profile+f' circuit{circuit} fresh300 trips',f.p(640+circuit),1)
            f.p(236,1)
            f.p(1,1)
            f.call('BoardErrAction')
            ck('T15-009',profile+f' circuit{circuit} leaving cooling clears low inhibit',f.p(640+circuit),0)

def eev_cleanup():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for reason in ('stopped','disabled','fault','communication'):
            f=init(profile)
            f.p(12,500)
            f.p(1153,200)
            f.p(1146,111)
            f.field(True,1,'CompControl',0,0 if reason=='stopped' else 1)
            f.field(False,1,'CompStatus',0,0 if reason=='stopped' else 5 if reason=='disabled' else 1 if reason=='fault' else 2)
            if reason=='disabled':f.p(1833,1)
            if reason=='communication':f.var('UnitCommErr',1,1,2)
            f.call('CompNormalStopAction')
            ck('T12-030',profile+' '+reason+' clears run request',f.field(True,1,'CompControl',0),0)
            ptr=0x20060000
            f.call('EEVSpecAutoAction',0,ptr,ptr+4,ptr+8,ptr+12)
            ck('T12-030',profile+' '+reason+' closes with normal seating travel',f.p(1145),220)
            for tick in range(11):
                f.var('uc1s',0)
                f.call('EEVSpecAutoAction',0,ptr,ptr+4,ptr+8,ptr+12)
                f.var('uc1s',1)
                f.call('EEVSpecAutoAction',0,ptr,ptr+4,ptr+8,ptr+12)
            ck('T12-030',profile+' '+reason+' closure completes',f.p(1145),0)
            ck('T12-030',profile+' '+reason+' does not touch next valve',f.p(1146),111)

def main():
    errors=[]
    for fn in (compatibility,winter_accepted_behavior,switch_ambiguity,coil_interruptions,eev_cleanup):
        try:fn()
        except Exception:
            errors.append({'function':fn.__name__,'traceback':traceback.format_exc()})
            traceback.print_exc()
    report={'hardware_access':False,'time_is_simulated':True,'cases':cases,'checks':checks,'errors':errors,
        'limits':'User-accepted electric minimum is an observation. T11-103 distinguishes two interpretations; no specification decision inferred.'}
    (D/'remaining529_compatibility_ARM.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print('COMPLETE',len(cases),len(checks),'mismatches',sum(not c['passed'] for c in checks),'errors',len(errors),flush=True)

if __name__=='__main__':main()
