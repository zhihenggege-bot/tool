"""Fixed physical 50 Hz AO span; preserve all unrelated bytes and 330 image."""
import hashlib
import json
import shutil
import build_timing_profiles as b
from test_defrost_lifecycle_arm import Firmware

R=b.ROOT
O=R/'.codex-tmp/vfd_scale_v1242_20261112'
OLD=R/'.codex-tmp/issuefix_v1059_v1241_20261111'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    O.mkdir(exist_ok=True)
    prior=json.loads((OLD/'BENCH_ONLY_3S/manifest.json').read_text('utf8'))
    before=prior['source_inventory']
    assert all(sha(R/p)==h for p,h in before.items()),'Baseline source changed'
    f=Firmware(OLD/'PRODUCTION/PSC316_V12.41_PRODUCTION.axf');rows=[]
    for maximum in (30,40,50):
        f.p(176,maximum)
        for hz in (5,20,maximum):
            rows.append(dict(maximum_hz=maximum,target_hz=hz,
                old_DA=f.call('OutdoorFanSpeed10ToDA',hz*10),required_DA=hz*20))
    (O/'old_scaling_reproduction.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    rel='PSC316RK-V12-外机/WELLTHINKER/User/UserAction.c'
    for name in (rel,'PSC316RK-V12-外机/WELLTHINKER/User/User.h'):
        p=R/name;data=p.read_bytes();dst=O/'source_backup'/name
        dst.parent.mkdir(parents=True,exist_ok=True);assert not dst.exists();dst.write_bytes(data)
        s=data.decode('latin1').replace('\r\n','\n')
        if name==rel:
            start=s.index('static signed int OutdoorFanSpeedToDA(')
            end=s.index('static void OutdoorFanSetSpeed(',start)
            s=s[:start]+'''static signed int OutdoorFanSpeedToDA(signed int Speed)
{
	long Output;
	/* V12.42: physical drive span is 0..10 V = 0..50 Hz.
	   FanMaxFreqSet limits targets, never the analog full scale. */
	if(Speed <= 0) return 0;
	Output = (long)Speed * 1000 / 50;
	if(Output > 1000) Output = 1000;
	if(Output < 0) Output = 0;
	return (signed int)Output;
}

static signed int OutdoorFanSpeed10ToDA(signed int Speed10)
{
	long Output;
	/* Speed10: 0.1 Hz; DA: 0.01 V, fixed 50 Hz physical span. */
	if(Speed10 <= 0) return 0;
	Output = (long)Speed10 * 1000 / 500;
	if(Output > 1000) Output = 1000;
	if(Output < 0) Output = 0;
	return (signed int)Output;
}

'''+s[end:]
        else:
            for old,new in (('PSC316_VERSION_MINOR 41','PSC316_VERSION_MINOR 42'),
                            ('PSC316_VERSION_DAY 11','PSC316_VERSION_DAY 12')):
                assert s.count(old)==1;s=s.replace(old,new)
        p.write_bytes(s.replace('\n','\r\n').encode('latin1'))
    after={p:sha(R/p) for p in before};changed=[p for p in before if before[p]!=after[p]]
    assert len(changed)==2
    for name,data in (('source_before.json',before),('source_after.json',after)):
        (O/name).write_text(json.dumps(data,indent=2),encoding='utf8')
    b.OUT=O
    for bench in (False,True):
        profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
        artifacts=b.build(*b.PROJECTS[1][:-1],'12.42',bench)
        m=json.loads((OLD/profile/'manifest.json').read_text('utf8'))
        for name,want in m['artifacts'].items():
            if name.startswith('PSC330_'):
                assert sha(OLD/profile/name)==want
                shutil.copy2(OLD/profile/name,O/profile/name);artifacts[name]=want
        assert all(sha(R/p)==h for p,h in after.items())
        m.update(artifacts=artifacts,source_inventory=after,changed_sources=changed,
            change='Fixed 0..10 V = 0..50 Hz outdoor fan AO scaling; maximum frequency only caps target',
            indoor_unchanged=True,outdoor_version='12.42',flashed=False,hardware_tested=False)
        (O/profile/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
        print('BUILD VERIFIED',profile,flush=True)

if __name__=='__main__':main()
