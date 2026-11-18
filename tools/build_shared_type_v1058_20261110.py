"""Build both 330 profiles and retain the exact, unchanged V12.40 outdoor images."""
import hashlib
import json
import shutil
import build_timing_profiles as b

b.OUT = b.ROOT / '.codex-tmp/shared_type_v1058_20261110'
old = b.ROOT / '.codex-tmp/shared_vfd_v1057_20261110'
before = json.loads((b.OUT / 'source_before.json').read_text('utf8'))
inventory = {p: hashlib.sha256((b.ROOT / p).read_bytes()).hexdigest() for p in before}
changed = [p for p in before if before[p] != inventory[p]]
assert set(changed) == {
    'PSC330RK-V10-内机/User/UserSrc/modulecontrol.c',
    'PSC330RK-V10-内机/User/UserHead/User.h',
    'PSC330RK-V10-内机/User/modbus/modbus.c',
}, changed
(b.OUT / 'source_after.json').write_text(json.dumps(inventory, indent=2)+'\n', 'utf8')
for bench in (False, True):
    profile = 'BENCH_ONLY_3S' if bench else 'PRODUCTION'
    artifacts = b.build(*b.PROJECTS[0][:-1], '10.58', bench)
    manifest = json.loads((old / profile / 'manifest.json').read_text('utf8'))
    for name, want in manifest['artifacts'].items():
        if name.startswith('PSC316_'):
            assert hashlib.sha256((old / profile / name).read_bytes()).hexdigest() == want
            shutil.copy2(old / profile / name, b.OUT / profile / name)
            artifacts[name] = want
    assert all(hashlib.sha256((b.ROOT / p).read_bytes()).hexdigest() == want
               for p, want in inventory.items())
    manifest.update(artifacts=artifacts, source_inventory=inventory,
                    changed_sources=changed, flashed=False, hardware_tested=False,
                    change='Share outdoor type/fan165/166, retaining independent source edits and legal pair protection',
                    shared_vfd_sources=[1340, 1341, 1342],
                    shared_type_sources={1343:165, 1344:166}, shared_parameter_count=25,
                    shared_type_stopped_only=True, outdoor_unchanged=True)
    (b.OUT / profile / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', 'utf8')
    print('BUILD OK', profile, flush=True)
