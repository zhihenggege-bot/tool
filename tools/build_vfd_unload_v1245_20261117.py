"""Byte-preserving single-VFD unload fix; build both profiles, no hardware."""
import json
import shutil
import build_timing_profiles as b
from build_manual_gate_v1244_20261113 import sha

R=b.ROOT
OLD=R/'.codex-tmp/manual_gate_v1063_v1244_20261113'
OUT=R/'.codex-tmp/vfd_unload_v1063_v1245_20261117'


def main():
    prior=json.loads((OLD/'BENCH_ONLY_3S/manifest.json').read_text('utf8'))
    before=prior['source_inventory']
    assert all(sha(R/n)==v for n,v in before.items())
    OUT.mkdir(exist_ok=False)
    for rel in ('PSC316RK-V12-外机/WELLTHINKER/User/UserAction.c',
                'PSC316RK-V12-外机/WELLTHINKER/User/User.h'):
        p=R/rel;raw=p.read_bytes();backup=OUT/'source_backup'/rel
        backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(raw)
        if rel.endswith('User.h'):
            for old,new in ((b'PSC316_VERSION_MINOR 44',b'PSC316_VERSION_MINOR 45'),
                            (b'PSC316_VERSION_DAY 13',b'PSC316_VERSION_DAY 17')):
                assert raw.count(old)==1;raw=raw.replace(old,new)
        else:
            old=b'\t\t\tif((OutdoorVfdSpeed > MinSpeed) && uc1s)\r\n\t\t\t{\r\n\t\t\t\tOutdoorVfdSpeed -= Step;\r\n\t\t\t}'
            new=b'\t\t\t/* V12.45: non-second scans must hold above-minimum speed. */\r\n\t\t\tif(OutdoorVfdSpeed > MinSpeed)\r\n\t\t\t{\r\n\t\t\t\tif(uc1s) OutdoorVfdSpeed -= Step;\r\n\t\t\t}'
            assert raw.count(old)==1;raw=raw.replace(old,new)
        p.write_bytes(raw)
    after={n:sha(R/n) for n in before}
    changed=[n for n in before if before[n]!=after[n]]
    assert len(changed)==2,changed
    for name,data in (('source_before.json',before),('source_after.json',after)):
        (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf8')
    b.OUT=OUT
    for bench in (False,True):
        profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
        artifacts=b.build(*b.PROJECTS[1][:-1],'12.45',bench)
        m=json.loads((OLD/profile/'manifest.json').read_text('utf8'))
        for name,digest in m['artifacts'].items():
            if name.startswith('PSC330_'):
                assert sha(OLD/profile/name)==digest
                shutil.copy2(OLD/profile/name,OUT/profile/name);artifacts[name]=digest
        assert all(sha(R/n)==v for n,v in after.items())
        m.update(artifacts=artifacts,source_inventory=after,new_changed_sources=changed,
                 change='Single VFD unload holds on non-second scans above minimum; stop only after ramp reaches minimum',
                 indoor_unchanged=True,outdoor_unchanged=False,indoor_version='10.63',outdoor_version='12.45',
                 flashed=False,hardware_tested=False)
        (OUT/profile/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
        print('BUILD VERIFIED',profile,flush=True)


if __name__=='__main__':main()
