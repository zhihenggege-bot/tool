"""Actual linked heating output functions, emulated inputs only.

Stage switch points are observations: the original drawings do not number all
horizontal thresholds. Only labelled topology, endpoints and SCR formula assert.
"""
import json
import traceback
from remaining529_offline_matrix_20261105 import init, ck, checks, cases, D


def outputs():
    points=sorted(set(range(0,1001,50))|{1,299,300,301,399,400,401,599,600,601,699,700,701,999})
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for owner,start,mode,share in (
            ('main',7,1,1),('shared reheat',11,0,1),
            ('independent reheat',15,0,0),('preheat',19,1,1)):
            for output_mode in range(1,5):
                cid=f'T06-{start+output_mode-1:03d}'
                f=init(profile,mode)
                f.p(129,share)
                f.p(128,2)
                region=0
                ptr=0x20060000
                observations=[]
                for demand in points+list(reversed(points)):
                    ispre=owner=='preheat'
                    prefix='Preheat' if ispre else 'Heat'
                    f.var('Indoor'+prefix+'AnalogMode',output_mode)
                    f.var('Indoor'+prefix+'AnalogDemand',demand)
                    if output_mode in (2,3):
                        level=f.call('IndoorSegLevel',demand,output_mode,ptr)
                        ck(cid,profile+f' stage{output_mode} demand{demand} bounded',0<=level<2**output_mode,True)
                        if demand==0:
                            # This sequencer deliberately advances at most one
                            # stage per invocation; observe until quiescent.
                            for _ in range(8):level=f.call('IndoorSegLevel',0,output_mode,ptr)
                            ck(cid,profile+' zero demand fully unloads',level,0)
                        if demand==1000:
                            for _ in range(8):level=f.call('IndoorSegLevel',1000,output_mode,ptr)
                            ck(cid,profile+' full demand reaches all binary groups',level,2**output_mode-1)
                        observations.append({'demand':demand,'binary_level':level})
                        continue
                    if output_mode==4:
                        # Independent oracle from the approved 400/700 load,
                        # 300/600 unload thresholds and the 40/30/30 capacities.
                        if demand==0:region=0
                        elif region==0 and demand>400:region=1
                        elif region==1:
                            if demand>700:region=2
                            elif demand<300:region=0
                        elif region==2 and demand<600:region=1
                        got=f.call('IndoorScrRegion',demand,ptr)
                        ck(cid,profile+f' SCR region demand{demand}',got,region)
                        f.var('Indoor'+prefix+'ScrRegion',got)
                    f.call('IndoorApplyHeatAnalogOutputs')
                    channel=1 if ispre else 9 if owner=='independent reheat' else 0
                    g1=int(region>=1 and demand>0) if output_mode==4 else 0
                    g2=int(region>=2 and demand>0) if output_mode==4 else 0
                    want=(max(0,min(400,demand-300*g1-300*g2))*1000+200)//400 if output_mode==4 else demand
                    ck(cid,profile+f' output demand{demand}',f.var('DA',index=channel,width=2),want)
                    for other in ({0,1,9}-{channel}):
                        ck(cid,profile+f' unused AO{other} demand{demand}',f.var('DA',index=other,width=2),0)
                    if output_mode==4:
                        slots=(13,14,15) if ispre else (0,1,2)
                        ck(cid,profile+f' SCR contactors demand{demand}',[f.var('output',index=i,width=1) for i in slots],[g1,g2,0])
                    observations.append({'demand':demand,'region':region,'ao':want,'groups':[g1,g2]})
                cases[cid].append({'profile':profile,'observed_curve':observations,
                    'stage_thresholds_are_observations':True,'passed':True})
        # Main/SCR and preheat/SCR can run concurrently on separate AO/DO.
        f=init(profile,1)
        f.p(129,1)
        for prefix,dem in (('Heat',850),('Preheat',950)):
            f.var('Indoor'+prefix+'AnalogMode',4)
            f.var('Indoor'+prefix+'AnalogDemand',dem)
            f.var('Indoor'+prefix+'ScrRegion',2)
        f.call('IndoorApplyHeatAnalogOutputs')
        ck('T06-023',profile+' parallel SCR AO independence',
           [f.var('DA',index=i,width=2) for i in (0,1)],[625,875])
        ck('T06-023',profile+' parallel SCR DO independence',
           [f.var('output',index=i,width=1) for i in (0,1,13,14)],[1,1,1,1])


def unused_sensors():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for mode in range(3):
            cid=f'T03-{117+mode:03d}'
            f=init(profile,mode)
            for a,v in {329:2,335:0,338:0,381:0,125:0,126:0,248:0,334:0,333:0,315:0}.items():f.p(a,v)
            for sensor in (0,1,2,3,4,7,8):
                f.var('SensorErr',1,sensor,1)
            f.call('BoardErrAction')
            ck(cid,profile+' unused optional probes do not stop thermal load',
               f.var('IndoorSensorPartialStopFlag',width=1),0)


def main():
    errors=[]
    for fn in (outputs,unused_sensors):
        print('START',fn.__name__,flush=True)
        try:fn()
        except Exception:
            errors.append({'function':fn.__name__,'traceback':traceback.format_exc()})
            traceback.print_exc()
    report={'hardware_access':False,'time_is_simulated':True,'cases':cases,'checks':checks,'errors':errors,
            'limits':'Stage thresholds observed, not assumed to be labelled in the specification; no physical output.'}
    (D/'remaining529_outputs_ARM.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print('COMPLETE',len(cases),'cases',len(checks),'checks','mismatches',sum(not c['passed'] for c in checks),'errors',len(errors),flush=True)


if __name__=='__main__':main()
