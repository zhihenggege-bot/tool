"""Build the minimal staged-preheat display fix for both profiles."""
import json,shutil,hashlib
import build_timing_profiles as b
b.OUT=b.ROOT/'.codex-tmp/preheat_stage_display_v1053_v1239_20261106'
OLD=b.ROOT/'.codex-tmp/fan_zero_target_v1052_v1239_20261105'
for bench in (False,True):
    profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
    artifacts=b.build(*b.PROJECTS[0][:-1],'10.53',bench,True)
    manifest=json.loads((OLD/profile/'manifest.json').read_text('utf8'))
    for name,want in manifest['artifacts'].items():
        if name.startswith('PSC316_'):
            assert hashlib.sha256((OLD/profile/name).read_bytes()).hexdigest()==want
            shutil.copy2(OLD/profile/name,b.OUT/profile/name);artifacts[name]=want
    manifest.update(artifacts=artifacts,flashed=False,hardware_tested=False,
        change='Preserve demand display for staged preheat while disabling its analog path; no stage/PID algorithm changes',
        outdoor_unchanged=True)
    (b.OUT/profile/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    print('BUILD OK',profile,flush=True)
