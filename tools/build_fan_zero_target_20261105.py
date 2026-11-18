"""Build both V10.52 330 profiles; preserve unchanged V12.39 316 images."""
import json,shutil,hashlib
import build_timing_profiles as b
b.OUT=b.ROOT/'.codex-tmp/fan_zero_target_v1052_v1239_20261105'
OLD=b.ROOT/'.codex-tmp/ai3_hold_reason_v1051_v1239_20261105'
for bench in (False,True):
    profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
    artifacts=b.build(*b.PROJECTS[0][:-1],'10.52',bench,True)
    manifest=json.loads((OLD/profile/'manifest.json').read_text('utf-8'))
    for name,want in manifest['artifacts'].items():
        if name.startswith('PSC316_'):
            assert hashlib.sha256((OLD/profile/name).read_bytes()).hexdigest()==want
            shutil.copy2(OLD/profile/name,b.OUT/profile/name);artifacts[name]=want
    manifest.update(artifacts=artifacts,flashed=False,hardware_tested=False,
                    outdoor_unchanged_from=str(OLD.relative_to(b.ROOT)))
    (b.OUT/profile/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n','utf-8')
    print('BUILD OK',profile,flush=True)
