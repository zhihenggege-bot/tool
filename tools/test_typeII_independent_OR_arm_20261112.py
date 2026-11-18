"""Full actual fan scan/interlock independent holds; temperatures explicitly stubbed."""
import json
import hashlib
from test_typeII_recovery_arm_20261112 import fixture, ROOT


def main():
    rows=[];traces=[];hashes={}
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        path=ROOT/'.codex-tmp/restart_guard_v1060_v1243_20261112'/profile/f'PSC316_V12.43_{profile}.axf'
        hashes[profile]=hashlib.sha256(path.read_bytes()).hexdigest()
        cond=[290];f=fixture(path,79,lambda:cond[0]);tick=0;timeline=[]
        def check(name,actual,expected):
            r=dict(profile=profile,name=name,actual=actual,expected=expected,passed=actual==expected)
            rows.append(r);assert r['passed'],r
        def segment(label,ambient,maximum,seconds):
            nonlocal tick
            cond[0]=maximum;f.p(1422,ambient)
            for _ in range(seconds):
                tick+=1;f.var('Systick_1ms',100000+tick*1000);f.var('uc1s',1)
                f.call('BoardFanControl');f.call('OutdoorProtectOutputLimit')
                timeline.append(dict(label=label,second=tick,ambient10=ambient,condensing_max10=maximum,
                    env_count=f.var('OutdoorTypeIILowRecoverEnvCount'),cond_count=f.var('OutdoorTypeIILowRecoverCondCount'),
                    low_off=f.var('OutdoorTypeIILowFanOff'),fan=f.p(874),
                    compressors=[f.var('output',index=i,width=1) for i in (0,1)]))
        segment('environment',101,290,18)
        segment('overlap',101,421,3)
        segment('condensing',79,421,16)
        check('combined37s_each_under30_no_restart',f.var('OutdoorTypeIILowFanOff'),1)
        check('environment_count_cleared',f.var('OutdoorTypeIILowRecoverEnvCount'),0)
        check('condensing19s',f.var('OutdoorTypeIILowRecoverCondCount'),19)
        segment('condensing_reaches30',79,421,11)
        check('independent30_releases_latch',f.var('OutdoorTypeIILowFanOff'),0)
        segment('stage_transition',79,421,20)
        check('fan_recovered',f.p(874),1)
        check('compressors_continuous',all(s['compressors']==[1,1] for s in timeline),True)
        traces.append(dict(profile=profile,samples=timeline))
    dest=ROOT/'测试证据/四项复核_20261112/restart_fix/typeII_independent_OR_ARM_results.json'
    dest.write_text(json.dumps(dict(total=len(rows),passed=sum(r['passed'] for r in rows),rows=rows,
        traces=traces,hardware_access=False,temperature_conversion_stubbed=True,AXF_SHA256=hashes),indent=2),encoding='utf8')
    print(len(rows),'independent OR full scan ARM checks passed')


if __name__=='__main__':main()
