"""Build separate production and isolated-load BENCH images with Keil.

Does not flash hardware or change the default Keil project definitions.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.codex-tmp/fan_enable_v1048_v1238_20261104'
PROJECTS = (
    ('330', 'PSC330RK-V10-内机/Project/PSC330RK-V10.uvprojx', 'MDK-32',
     'Obj', 'PSC330RK-V10', '10.48'),
    ('316', 'PSC316RK-V12-外机/USER/PSC316RK-V12.uvprojx', 'PSC316RK', '../OBJ',
     'PSC316RK-V12-20250327', '12.38'),
)
KEIL = Path('D:/Keil_v5/UV4/UV4.exe')


def build(model, rel, target, obj_dir, stem, version, bench, incremental=False):
    source = ROOT / rel
    raw = source.read_text(encoding='utf-8-sig')
    # Never inherit a developer's BENCH define into a production package.
    raw = re.sub(r'([,;])?PSC_BENCH_TIMING\s*=\s*\d+', '', raw)
    targets = re.findall(r'<TargetName>(.*?)</TargetName>', raw)
    assert len(targets) == 1, targets
    target = targets[0]
    profile = 'BENCH_ONLY_3S' if bench else 'PRODUCTION'
    project = source
    if bench:
        raw, n = re.subn(r'(<Define>)([^<]*USE_STDPERIPH_DRIVER[^<]*)(</Define>)',
                         r'\1\2,PSC_BENCH_TIMING=1\3', raw)
        assert n == 1
        bench_output = '.\\BenchObj\\'
        raw, n = re.subn(r'<OutputDirectory>[^<]*</OutputDirectory>',
                         lambda m: '<OutputDirectory>' + bench_output + '</OutputDirectory>', raw)
        assert n == 1
        raw = re.sub(r'<ListingPath>[^<]*</ListingPath>',
                     lambda m: '<ListingPath>' + bench_output + '</ListingPath>', raw)
        project = source.with_name(source.stem + '_BENCH_ONLY.uvprojx')
        project.write_text(raw, encoding='utf-8', newline='\r\n')
        obj_dir = 'BenchObj'
    elif raw != source.read_text(encoding='utf-8-sig'):
        raise AssertionError('Default project contains PSC_BENCH_TIMING: restore production defaults first')
    dest = OUT / profile
    dest.mkdir(parents=True, exist_ok=True)
    log = dest / f'build{model}.log'
    proc = subprocess.run([str(KEIL), '-b' if incremental else '-r', str(project), '-t', target, '-o', str(log)])
    data = log.read_text(encoding='utf-8-sig', errors='replace')
    assert proc.returncode == 0 and '0 Error(s), 0 Warning(s)' in data, data[-5000:]
    artifacts = {}
    for suffix in ('.axf', '.hex'):
        src = source.parent / obj_dir / (stem + suffix)
        dst = dest / f'PSC{model}_V{version}_{profile}{suffix}'
        shutil.copy2(src, dst)
        artifacts[dst.name] = hashlib.sha256(dst.read_bytes()).hexdigest()
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('production', 'bench', 'all'), default='all')
    parser.add_argument('--incremental', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--indoor-version')
    parser.add_argument('--outdoor-version')
    args = parser.parse_args()
    global OUT, PROJECTS
    if args.output:
        OUT = args.output if args.output.is_absolute() else ROOT / args.output
    PROJECTS = tuple(p[:-1]+((args.indoor_version if p[0]=='330' else args.outdoor_version) or p[-1],)
                     for p in PROJECTS)
    for bench in (False, True):
        if args.profile != 'all' and (args.profile == 'bench') != bench:
            continue
        artifacts = {}
        for project in PROJECTS:
            artifacts.update(build(*project, bench, args.incremental))
        folder = OUT / ('BENCH_ONLY_3S' if bench else 'PRODUCTION')
        manifest = {
            'bench_only': bench,
            'profile_marker_1299': 0x3B03 if bench else 0,
            'ambient_recovery_1298_default_seconds': 3 if bench else 300,
            'minimum_stop_floor_seconds': 3 if bench else 120,
            'minimum_run_floor_seconds': 3 if bench else 180,
            'sequence_timing_seconds': {
                'normal_compressor_action_gap': 3 if bench else 30,
                'defrost_all_stopped_recovery': 5 if bench else 60,
                'ordinary_start_with_dampers': 5 if bench else 150,
                'ordinary_start_without_dampers': 3 if bench else 10,
                'fan_pressure_confirmation': 3 if bench else 10,
                'normal_fans_stopped_to_damper_close': 3 if bench else 30,
                'outdoor_normal_fan_action_gap': 3 if bench else 15,
                'fan_configured_delay_cap': 3 if bench else None,
            },
            'configured_fan_delay_sign_and_zero_preserved': True,
            'artifacts': artifacts, 'flashed': False, 'hardware_tested': False,
        }
        (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        print(folder)


if __name__ == '__main__':
    main()
