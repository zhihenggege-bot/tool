"""Build330 ambient-scope correction; copy unchanged316; never flash hardware."""
import hashlib
import json
import shutil
import build_timing_profiles as b

OLD = b.ROOT / '.codex-tmp/restart_guard_v1060_v1243_20261112'
OUT = b.ROOT / '.codex-tmp/ambient_scope_v1061_20261112'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    before = json.loads((OUT / 'source_before.json').read_text('utf8'))
    after = {name: sha(b.ROOT / name) for name in before}
    changed = sorted(name for name in before if before[name] != after[name])
    assert changed == ['PSC330RK-V10-内机/User/UserHead/User.h',
                       'PSC330RK-V10-内机/User/UserSrc/CompAction.c'], changed
    assert not (OUT / 'PRODUCTION/manifest.json').exists(), 'Preserve earlier builds'
    (OUT / 'source_after.json').write_text(json.dumps(after, indent=2), encoding='utf8')
    b.OUT = OUT
    for bench in (False, True):
        profile = 'BENCH_ONLY_3S' if bench else 'PRODUCTION'
        artifacts = b.build(*b.PROJECTS[0][:-1], '10.61', bench)
        previous = json.loads((OLD / profile / 'manifest.json').read_text('utf8'))
        for name, digest in previous['artifacts'].items():
            if not name.startswith('PSC316_'):
                continue
            assert sha(OLD / profile / name) == digest
            shutil.copy2(OLD / profile / name, OUT / profile / name)
            artifacts[name] = digest
        assert all(sha(b.ROOT / name) == digest for name, digest in after.items())
        previous.update(artifacts=artifacts, source_inventory=after,
                        new_changed_sources=changed,
                        changed_sources=sorted(set(previous['changed_sources'] + changed)),
                        change='330 uses per-unit316 ambient protection;737 summarizes all configured units blocked',
                        indoor_version='10.61', outdoor_version='12.43',
                        outdoor_unchanged=True, indoor_unchanged=False,
                        flashed=False, hardware_tested=False)
        (OUT / profile / 'manifest.json').write_text(
            json.dumps(previous, indent=2) + '\n', encoding='utf8')
        print('BUILD VERIFIED', profile, flush=True)


if __name__ == '__main__':
    main()
