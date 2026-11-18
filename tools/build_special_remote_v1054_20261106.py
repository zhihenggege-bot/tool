"""Build both common-source profiles; retain hash-identical 316 images."""
import hashlib
import json
import shutil
import build_timing_profiles as b

b.OUT=b.ROOT/'.codex-tmp/special_remote_v1054_v1239_20261106'
OLD=b.ROOT/'.codex-tmp/preheat_stage_display_v1053_v1239_20261106'
for bench in (False,True):
    profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
    artifacts=b.build(*b.PROJECTS[0][:-1],'10.54',bench,True)
    manifest=json.loads((OLD/profile/'manifest.json').read_text('utf8'))
    for name,want in manifest['artifacts'].items():
        if name.startswith('PSC316_'):
            assert hashlib.sha256((OLD/profile/name).read_bytes()).hexdigest()==want
            shutil.copy2(OLD/profile/name,b.OUT/profile/name)
            artifacts[name]=want
    manifest.update(artifacts=artifacts,flashed=False,hardware_tested=False,
        change='Preserve pending remote-interlock restart at special-mode shutdown completion',outdoor_unchanged=True)
    (b.OUT/profile/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n','utf8')
    print('BUILD OK',profile,flush=True)
