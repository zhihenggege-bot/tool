"""Actual ARM regressions, including old/new automatic-output comparison."""
import itertools
import json
from test_defrost_lifecycle_arm import Firmware, ROOT

O=ROOT/'.codex-tmp/manual_gate_v1244_20261113'
OLD=ROOT/'.codex-tmp/ambient_scope_v1061_20261112'

def fixture(path,pair):
    f=Firmware(path)
    for a,v in {1:1,107:1,165:pair[0],166:pair[1]}.items():f.p(a,v)
    assert f.call('OutdoorFanConfigurationValid')==1
    assert f.call('OutdoorPressureConfigurationValid')==1
    return f

def output(f):return [f.var('output',index=i,width=1) for i in range(8)]

def init(f,manual,fans,ao,automatic=(0,0)):
    for a,v in {1300:manual,1302:1,1303:1,1304:fans[0],1305:fans[1],1306:1,1307:1,1308:1,1309:fans[2],
                872:automatic[0],874:automatic[1],800:0,801:0,1406:0,167:0,152:0,153:0}.items():f.p(a,v)
    f.var('UnitLevelFault',0);f.var('AmbientLockout',0);f.var('OutdoorFanRegulationStop',0)
    f.var('DA',ao,index=0,width=4)
    for i,v in enumerate([1,1,fans[0],fans[1],1,1,1,fans[2]]):f.var('output',v,i,1)

def main():
    rows=[]
    for bench in (False,True):
        profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
        auto_count=0;manual_count=0
        for pair in ((0,0),(0,1),(1,2),(1,3),(2,2),(2,4)):
            f=fixture(O/profile/f'PSC316_V12.44_{profile}.axf',pair)
            old=fixture(OLD/profile/f'PSC316_V12.43_{profile}.axf',pair)
            for fans,ao,automatic in itertools.product(itertools.product((0,1),repeat=3),(0,600),itertools.product((0,1),repeat=2)):
                for q in (old,f):
                    init(q,0,fans,ao,automatic);q.call('OutdoorProtectOutputLimit')
                assert output(f)==output(old),(profile,pair,fans,ao,automatic,output(old),output(f))
                auto_count+=1
            for fans,ao,automatic in itertools.product(itertools.product((0,1),repeat=3),(0,600),((0,0),(1,1))):
                init(f,1,fans,ao,automatic);f.call('HandDebugY02Ctrl');f.call('OutdoorProtectOutputLimit')
                fan=pair[1]
                ready=bool((fans[0] or fans[2]) if fan==0 else (fans[0] or fans[1]) if fan==1 else (fans[0] and ao>0) if fan in (2,4) else any(fans))
                assert output(f)[:2]==[int(ready)]*2,(profile,pair,fans,ao,automatic,output(f))
                assert not(output(f)[2] and output(f)[7]) if fan==0 else True
                assert not(output(f)[3] and output(f)[7]) if fan==3 else True
                manual_count+=1
            for field,val,want in ((800,1,[0,1]),(801,1,[1,0]),(167,1,[0,0]),(152,1,[0,1]),(153,1,[1,0]),(1406,1,[0,0])):
                init(f,1,(1,0,0),600);f.p(field,val)
                f.call('HandDebugY02Ctrl');f.call('OutdoorProtectOutputLimit')
                assert output(f)[:2]==want,(profile,pair,field,output(f))
                if field==1406:assert not any(output(f))
            init(f,1,(1,0,0),600);f.var('UnitLevelFault',1)
            f.call('HandDebugY02Ctrl');f.call('OutdoorProtectOutputLimit')
            assert not any(output(f)[i] for i in (0,1,2,3,4,5,7))
        rows.append(dict(profile=profile,automatic_old_new_equal=auto_count,manual_fan_cases=manual_count,
                         fault_disable_emergency_cases=42,passed=True))
        print('ARM REGRESSION PASS',rows[-1],flush=True)
    (O/'ARM_regression.json').write_text(json.dumps(dict(hardware_access=False,results=rows),indent=2),encoding='utf8')

if __name__=='__main__':main()
