"""Fix manual fan readiness and retain final fault clamps; no hardware access."""
import hashlib
import json
import shutil
import build_timing_profiles as b

R=b.ROOT
OLD=R/'.codex-tmp/ambient_scope_v1061_20261112'
OUT=R/'.codex-tmp/manual_gate_v1244_20261113'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    prior=json.loads((OLD/'BENCH_ONLY_3S/manifest.json').read_text('utf8'))
    before=prior['source_inventory']
    assert all(sha(R/p)==v for p,v in before.items())
    OUT.mkdir(exist_ok=False)
    for rel in ('PSC316RK-V12-外机/WELLTHINKER/User/UserAction.c',
                'PSC316RK-V12-外机/WELLTHINKER/User/User.h'):
        p=R/rel;raw=p.read_bytes();backup=OUT/'source_backup'/rel
        backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(raw)
        if rel.endswith('User.h'):
            assert raw.count(b'PSC316_VERSION_MINOR 43')==1
            raw=raw.replace(b'PSC316_VERSION_MINOR 43',b'PSC316_VERSION_MINOR 44')
            raw=raw.replace(b'PSC316_VERSION_DAY 12',b'PSC316_VERSION_DAY 13')
        else:
            old=b'''\t/* [V12.10] Manual debug owns the DOs: this function runs AFTER\r
\t   HandDebugY02Ctrl() in the scan, so any clamp here would undo the\r
\t   operator's command. Machine-type limits resume when [1300] goes 0. */'''
            assert raw.count(old)==1
            raw=raw.replace(old,b'\t/* Manual commands remain subject to final safety and fan interlocks. */')
            marker=b'\tif(Comp1Enable)\r\n'
            start=raw.index(b'void OutdoorProtectOutputLimit(void)')
            pos=raw.index(marker,start)
            safety='''	/* V12.44: ErrorProcess precedes manual DO assignment. Reapply its
	   existing fault result here so manual commands cannot undo protection. */
	if(HandDebug == 1)
	{
		if(UnitLevelFault || UrgencyStop)
		{
			OutdoorFanAllOff();
			Y00 = 0; Y01 = 0; Y02 = 0; Y03 = 0;
			Y04 = 0; Y05 = 0; Y07 = 0;
			if(UrgencyStop) Y06 = 0;
			return;
		}
		if(Comp1Err) { Y00 = 0; Y04 = 0; }
		if(Comp2Err) { Y01 = 0; Y05 = 0; }
	}

'''.replace('\n','\r\n').encode('ascii')
            raw=raw[:pos]+safety+raw[pos:]
            old='''		OutdoorFanPhysicalState(&Fan1On,&Fan2On);
		FanReady = (Fan1On || Fan2On) ? 1 : 0;
		if((OutdoorFanTypeSet == 2) || (OutdoorFanTypeSet == 4))
		{
			if((FanOpenSet == 0) || (DA0value <= 0)) FanReady = 0;
		}
		/* [25-0427R-DX] Manual mode: HandDebugY02Ctrl drives Y00/Y01 directly;
		   do not cut the compressors from the normal fan state. */'''.replace('\n','\r\n').encode('ascii')
            new='''		if(HandDebug == 1)
		{
			/* Manual DOs do not update automatic FanOpenSet/FanOpenSet2.
			   Count only outputs supported by the configured fan type. */
			switch(OutdoorFanTypeSet)
			{
				case 0: FanReady = (Fan1Y03 || Fan2HighY04) ? 1 : 0; break;
				case 1: FanReady = (Fan1Y03 || Fan3Y07) ? 1 : 0; break;
				case 2:
				case 4: FanReady = (Fan1Y03 && DA0value > 0) ? 1 : 0; break;
				case 3: FanReady = (Fan1Y03 || Fan3Y07 || Fan2HighY04) ? 1 : 0; break;
				default: FanReady = 0; break;
			}
		}
		else
		{
			OutdoorFanPhysicalState(&Fan1On,&Fan2On);
			FanReady = (Fan1On || Fan2On) ? 1 : 0;
			if((OutdoorFanTypeSet == 2) || (OutdoorFanTypeSet == 4))
			{
				if((FanOpenSet == 0) || (DA0value <= 0)) FanReady = 0;
			}
		}'''.replace('\n','\r\n').encode('ascii')
            assert raw.count(old)==1;raw=raw.replace(old,new)
        p.write_bytes(raw)
    after={p:sha(R/p) for p in before}
    changed=[p for p in before if before[p]!=after[p]]
    assert len(changed)==2,changed
    for name,data in (('source_before.json',before),('source_after.json',after)):
        (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf8')
    b.OUT=OUT
    for bench in (False,True):
        profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
        artifacts=b.build(*b.PROJECTS[1][:-1],'12.44',bench)
        m=json.loads((OLD/profile/'manifest.json').read_text('utf8'))
        for name,digest in m['artifacts'].items():
            if name.startswith('PSC330_'):
                assert sha(OLD/profile/name)==digest
                shutil.copy2(OLD/profile/name,OUT/profile/name);artifacts[name]=digest
        assert all(sha(R/p)==v for p,v in after.items())
        m.update(artifacts=artifacts,source_inventory=after,new_changed_sources=changed,
                 change='Manual fan readiness reads supported DO/AO; final manual fault/estop clamps',
                 indoor_unchanged=True,outdoor_unchanged=False,outdoor_version='12.44',
                 flashed=False,hardware_tested=False)
        (OUT/profile/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
        print('BUILD VERIFIED',profile,flush=True)

if __name__=='__main__':main()
