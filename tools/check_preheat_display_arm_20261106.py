"""Whole producer/enforcement check of the discovered display regression."""
import json
import remaining529_offline_matrix_20261105 as base
from test_defrost_lifecycle_arm import Firmware
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NEW=ROOT/'.codex-tmp/preheat_stage_display_v1053_v1239_20261106'
OLD=base.P
rows=[]
for version,package in (('10.52',OLD),('10.53',NEW)):
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for mode in range(5):
            f=Firmware(str(package/profile/f'PSC330_V{version}_{profile}.axf'))
            f.uc.mem_map(0x22000000,0x100000);f.call('ParameterInit')
            for a in range(500):f.p(a,f.var('Parameter_def',index=a,width=2))
            for a,v in {1:1,236:1,709:2,700:4,128:0,127:0,333:mode,
                374:0,356:100,357:0,512:0,346:0,329:2,330:0,331:0,
                335:0,336:0,337:0,338:0,381:0,332:0}.items():f.p(a,v)
            for _ in range(8):f.call('PreHeatControl');f.call('IndoorEnforceConfiguredOutputDisable')
            demand=f.p(891);contacts=[f.var('output',index=i,width=1) for i in (13,14,15)]
            before={'demand':demand,'DO':contacts,'AO1':f.var('DA',index=1,width=2)}
            expected=0 if mode==0 else 1000
            correct=demand==expected and (contacts==[1,1,0] if mode in (2,4) else contacts==[1,1,1] if mode==3 else contacts==[0,0,0])
            if mode in (0,2,3):correct&=before['AO1']==0
            else:correct&=before['AO1']==1000
            if version=='10.53':assert correct,(profile,mode,before)
            # Disabling the configured preheater must still clear all its paths.
            f.p(333,0);f.call('PreHeatControl');f.call('IndoorEnforceConfiguredOutputDisable')
            after={'demand':f.p(891),'DO':[f.var('output',index=i,width=1) for i in (13,14,15)],'AO1':f.var('DA',index=1,width=2)}
            assert after=={'demand':0,'DO':[0,0,0],'AO1':0},after
            rows.append({'version':version,'profile':profile,'mode':mode,'enabled':before,'disabled':after,'enabled_matches':bool(correct)})
            print(version,profile,mode,before,'correct',correct,flush=True)
out=ROOT/'测试证据/内机实测_20261105/BENCH_V1053_V1239/preheat_display_ARM_20261106.json'
out.write_text(json.dumps({'hardware_access':False,'simulation':True,'checks':rows},ensure_ascii=False,indent=2),encoding='utf8')
assert sum(not r['enabled_matches'] for r in rows if r['version']=='10.52')==4
print('Old defect reproduced in both profiles; new AO/stage/SCR/disable checks pass',flush=True)
