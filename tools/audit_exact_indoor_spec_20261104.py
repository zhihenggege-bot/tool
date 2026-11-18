"""Read-only actual ARM audit of newly supplied exact indoor spec. No hardware."""
import sys, json, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_indoor_fan_enable_arm import board, final, state, ao, out, D

observations = []
curves = []
def snap(f):
    return {'mode':f.p(236),'heat_fault':f.p(924),'humid_demand':f.p(892),
            'DA2':ao(f,2),'humid_DO':out(f,13),'AI3Err':f.p(617),
            'sensor_partial_stop':f.var('IndoorSensorPartialStopFlag',width=1),
            'SysErrStatus':f.p(710),'SysStep':f.p(709),'fan_fallback':f.p(954)}

for bench in (False,True):
    profile = 'BENCH_ONLY_3S' if bench else 'PRODUCTION'
    for mode in (0,1):
        for fault in ('X06_En','X07_En'):
            for output in (1,2):
                f=board(bench,mode=mode);f.p(709,2);f.var('X_02',1)
                for a,v in {125:1,126:1,248:1,334:output,168:1,169:1,
                            738:250,739:250,512:50,500:500,501:300,
                            128:2,127:1,332:1,333:1}.items():f.p(a,v)
                f.call('HumidtCtrl');before=snap(f)
                assert before['humid_demand']==1000,'fixture must start humidifying'
                f.var(fault,1,width=1) # already filtered input; NOT a DI filter timing test
                f.call('BoardErrAction');f.call('HumidtCtrl');final(f);after=snap(f)
                observations.append({'id':'3.11.9','profile':profile,'fault':fault,
                    'output':'AO' if output==1 else 'DO','before':before,'after':after,
                    'expected':'Faulted heater off and humidifier demand/DO/AO all zero in either mode',
                    'spec_pass':after['heat_fault']==1 and after['humid_demand']==0 and
                                after['DA2']==0 and after['humid_DO']==0})
    for mode in (0,1,2):
        for sensor,reg in [('AI3',617),('room_NTC_positive_control',618)]:
            f=board(bench,mode=mode);f.p(709,2);f.var('X_02',1)
            for a,v in {329:3,128:2,127:1,332:1,333:0,315:0,
                        738:250,739:250,512:50,501:500,1265:1}.items():f.p(a,v)
            state(f)
            f.call('BoardErrAction');before=snap(f)
            f.p(reg,1);f.call('BoardErrAction');f.call('FanAction');after=snap(f)
            assert before['sensor_partial_stop']==0 and before['SysErrStatus']==0,'clean fixture'
            observations.append({'id':'3.11.8','profile':profile,'sensor':sensor,
                'before':before,'after':after,'expected_partial_stop':int(mode!=2),
                'scope':'Actual fault aggregator and fan fallback; no physical signal generator or full scheduler',
                'spec_pass':after['sensor_partial_stop']==int(mode!=2)})
    # Capture stateful curves and residual AO from actual compiled functions.
    for count in (2,3):
        f=board(bench);ptr=0x20060000;f.write(ptr,0)
        for direction,demands in [('up',range(0,1001,5)),('down',range(1000,-1,-5))]:
            last=None
            for demand in demands:
                level=f.call('IndoorSegLevel',demand,count,ptr)
                if level!=last:
                    curves.append({'profile':profile,'type':f'1:2{":4" if count==3 else ""}',
                                  'direction':direction,'sampled_demand':demand,'level':level,
                                  'note':'5/1000 sampling; exact comparators are in source, not inferred from diagram'})
                    last=level
    f=board(bench);ptr=0x20060000;f.write(ptr,0)
    for direction,demands in [('up',[0,299,300,301,399,400,401,599,600,601,699,700,701,1000]),
                              ('down',[1000,701,700,699,601,600,599,401,400,399,301,300,299,0])]:
        for demand in demands:
            region=f.call('IndoorScrRegion',demand,ptr)
            f.call('IndoorSetScrOutputs',demand,region,ptr+16,ptr+20,ptr+24)
            a,g1,g2=f.read(ptr+16,2),f.read(ptr+20,1),f.read(ptr+24,1)
            expected=(max(0,min(400,demand-300*g1-300*g2))*1000+200)//400
            assert a==expected
            curves.append({'profile':profile,'type':'SCR40/30/30','direction':direction,
                           'demand':demand,'region':region,'AO':a,'group1':g1,'group2':g2,
                           'equivalent_total_permille':a*0.4+300*g1+300*g2})

dest=ROOT/'.codex-tmp/exact_indoor_spec_20261104';dest.mkdir(exist_ok=True)
result={'scope':'Offline execution of actual V10.48 ARM only, never connected to hardware',
        'observations':observations,'curves':curves,
        'artifacts_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in D.glob('*/*330*.axf')}}
(dest/'observations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
for row in observations:
    print(row['profile'],row['id'],row.get('fault',row.get('sensor')),row.get('output',''),
          'mode',row['after']['mode'],'PASS' if row['spec_pass'] else 'MISMATCH',row['after'])
print('Observations',len(observations),'curve samples',len(curves))
