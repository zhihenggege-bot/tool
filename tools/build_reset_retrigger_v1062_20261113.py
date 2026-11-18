"""Rearm the existing 11-second outdoor reset pulse on every new request."""
import json
import shutil
import build_timing_profiles as b
from build_manual_gate_v1244_20261113 import sha
from test_defrost_lifecycle_arm import Firmware

R=b.ROOT;OLD=R/'.codex-tmp/manual_gate_v1244_20261113';OUT=R/'.codex-tmp/manual_gate_v1062_v1244_20261113'

def observe(path):
    f=Firmware(path);f.uc.mem_map(0x22000000,0x100000);f.var('uc1s',1)
    f.p(524,1);f.call('ErrorReset')
    f.var('uc1s',0);f.p(524,0);f.call('ErrorReset');f.var('uc1s',1)
    for _ in range(8):f.call('ErrorReset')
    before=f.var('COUNT1');f.p(524,1);f.call('ErrorReset')
    rows=[dict(seconds=0,count=f.var('COUNT1'),reset=f.p(1402))]
    for second in range(1,12):
        f.call('ErrorReset');rows.append(dict(seconds=second,count=f.var('COUNT1'),reset=f.p(1402)))
    return dict(before_retrigger_count=before,rows=rows)

def prepare_sources():
    m=json.loads((OLD/'BENCH_ONLY_3S/manifest.json').read_text('utf8'));before=m['source_inventory']
    assert all(sha(R/n)==v for n,v in before.items())
    OUT.mkdir(exist_ok=False)
    for rel in ('PSC330RK-V10-内机/User/UserHead/User.h','PSC330RK-V10-内机/User/UserSrc/ErrorCheck.c'):
        p=R/rel;raw=p.read_bytes();backup=OUT/'source_backup'/rel
        backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(raw)
        if rel.endswith('User.h'):
            assert raw.count(b'PSC330_VERSION_MINOR        61')==1
            raw=raw.replace(b'PSC330_VERSION_MINOR        61',b'PSC330_VERSION_MINOR        62')
            raw=raw.replace(b'PSC330_VERSION_DAY          12',b'PSC330_VERSION_DAY          13')
        else:
            old=b'\t\tMODresetfalg=1;\r\n';assert raw.count(old)==1
            raw=raw.replace(old,b'\t\t/* V10.62: a new reset must receive a full transmission window. */\r\n\t\tCOUNT1=0;\r\n'+old)
        p.write_bytes(raw)
    after={n:sha(R/n) for n in before};changed=[n for n in before if before[n]!=after[n]]
    assert len(changed)==2
    for name,data in (('source_before.json',before),('source_after.json',after)):
        (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf8')
    return after,changed

def main():
    if OUT.exists():
        after=json.loads((OUT/'source_after.json').read_text('utf8'))
        before=json.loads((OUT/'source_before.json').read_text('utf8'))
        assert all(sha(R/n)==v for n,v in after.items())
        changed=[n for n in before if before[n]!=after[n]]
    else:after,changed=prepare_sources()
    b.OUT=OUT;regression=[]
    for bench in (False,True):
        profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
        existing=OUT/profile/'manifest.json'
        if existing.exists():
            saved=json.loads(existing.read_text('utf8'))
            assert all(sha(OUT/profile/n)==v for n,v in saved['artifacts'].items())
            artifacts={n:v for n,v in saved['artifacts'].items() if n.startswith('PSC330_')}
        else:artifacts=b.build(*b.PROJECTS[0][:-1],'10.62',bench)
        m=json.loads((OLD/profile/'manifest.json').read_text('utf8'))
        for n,v in m['artifacts'].items():
            if n.startswith('PSC316_'):
                assert sha(OLD/profile/n)==v
                shutil.copy2(OLD/profile/n,OUT/profile/n);artifacts[n]=v
        assert all(sha(R/n)==v for n,v in after.items())
        m.update(artifacts=artifacts,source_inventory=after,indoor_version='10.62',outdoor_version='12.44',
                 indoor_unchanged=False,outdoor_unchanged=True,new_changed_sources=changed,
                 change='Manual readiness/final fault clamps plus full11s reset pulse for each new reset request',
                 flashed=False,hardware_tested=False)
        (OUT/profile/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
        old=observe(OLD/profile/f'PSC330_V10.61_{profile}.axf')
        new=observe(OUT/profile/f'PSC330_V10.62_{profile}.axf')
        assert old['rows'][1]['reset']==0
        assert all(r['reset']==1 for r in new['rows'][:10])
        assert new['rows'][10]['reset']==0
        regression.append(dict(profile=profile,before=old,after=new,passed=True))
        print('BUILD AND RESET RETRIGGER ARM VERIFIED',profile,flush=True)
    (OUT/'reset_ARM_regression.json').write_text(json.dumps(regression,indent=2),encoding='utf8')

if __name__=='__main__':main()
