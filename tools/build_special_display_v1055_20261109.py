"""Both profiles from common source; retain identical 316 artifacts."""
import hashlib,json,shutil
import build_timing_profiles as b
b.OUT=b.ROOT/'.codex-tmp/special_display_v1055_v1239_20261109'
OLD=b.ROOT/'.codex-tmp/special_remote_v1054_v1239_20261106'
inventory=json.loads((b.OUT/'source_change_manifest.json').read_text('utf8'))['source_inventory_after']
for bench in (False,True):
    profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
    artifacts=b.build(*b.PROJECTS[0][:-1],'10.55',bench,True)
    manifest=json.loads((OLD/profile/'manifest.json').read_text('utf8'))
    for name,want in manifest['artifacts'].items():
        if name.startswith('PSC316_'):
            assert hashlib.sha256((OLD/profile/name).read_bytes()).hexdigest()==want
            shutil.copy2(OLD/profile/name,b.OUT/profile/name);artifacts[name]=want
    assert all(hashlib.sha256((b.ROOT/p).read_bytes()).hexdigest()==want for p,want in inventory.items())
    manifest.update(artifacts=artifacts,source_inventory=inventory,flashed=False,hardware_tested=False,
        change='Clear special-phase display on emergency fault stop only',outdoor_unchanged=True)
    (b.OUT/profile/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n','utf8')
    print('BUILD OK',profile,flush=True)
