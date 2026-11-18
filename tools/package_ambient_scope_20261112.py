"""Package unflashedV10.61 and offline monitor; leave paused bench untouched."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / '.codex-tmp/ambient_scope_v1061_20261112'
EVIDENCE = ROOT / '测试证据/环境联锁修复_20261112'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def archive(folder):
    files = sorted(p for p in folder.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.txt')
    (folder / 'SHA256SUMS.txt').write_text(''.join(
        sha(p) + '  ' + p.relative_to(folder).as_posix() + '\n' for p in files), encoding='utf8')
    target = folder.with_name(folder.name + '.zip')
    assert not target.exists(), target
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():
                z.write(p, p.relative_to(folder).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for p in folder.rglob('*'):
            if p.is_file():
                assert hashlib.sha256(z.read(p.relative_to(folder).as_posix())).hexdigest() == sha(p)
    return dict(path=str(target.relative_to(ROOT)), sha256=sha(target), archive_verified=True)


def main():
    assert json.loads((ROOT / '测试证据/剩余全队列_20261112/controller.json').read_text('utf8'))['status'] == 'paused_by_user'
    assert (ROOT / '.codex-tmp/continuous_v1055_pause.request').exists()
    smoke = json.loads((BUILD / 'monitor_exe_smoke.json').read_text('utf8'))
    tests = json.loads((EVIDENCE / 'monitor_tests.json').read_text('utf8'))
    assert smoke['version'] == tests['version'] == 'FFP-2026.11.12b'
    assert smoke['gui_created'] and not smoke['serial_opened']
    assert tests['passed'] == tests['total'] == 354
    source = ROOT / 'psc330_monitor_tool/psc330_monitor'
    assert tests['source_sha256'] == sha(source / 'app.py')
    toc = (BUILD / 'pyinstaller/PSC330_PSC316_Monitor/Analysis-00.toc').read_text('utf8')
    assert 'pt_tables' in toc and 'serial.serialwin32' in toc
    monitor = ROOT / '监控工具_FFP-2026.11.12b'
    assert not monitor.exists(), monitor
    monitor.mkdir()
    for name in ('app.py', 'pt_tables.py', 'README.md', 'test_fault_summary.py', 'PSC330_PSC316_Monitor.spec'):
        copy(source / name, monitor / 'Python源码' / name)
    copy(BUILD / 'monitor_dist/PSC330_PSC316_Monitor.exe', monitor / 'PSC330_PSC316_Monitor.exe')
    copy(BUILD / 'monitor_exe_smoke.json', monitor / 'monitor_exe_smoke.json')
    copy(EVIDENCE / 'monitor_tests.json', monitor / 'monitor_tests.json')
    (monitor / '使用说明.txt').write_text(
        'PSC330 / PSC316监控工具 FFP-2026.11.12b\n'
        '双击EXE运行，无需安装Python。\n'
        '330 V10.61起，737显示全部已配置且启用外机的环境禁止汇总。\n'
        '逐机环境禁止/故障看2598～2601；旧固件737仍是旧环境联锁含义。\n'
        '保留0～10V对应0～50Hz及逐条故障/ERR交叉显示。\n'
        '本次只更新737说明及软件版本，未改通讯或写入行为。\n'
        '新固件尚未烧录，台架复测安排明天。\n', encoding='utf8')
    monitor_zip = archive(monitor)
    dest = ROOT / '发布包_330V10.61_316V12.43_20261112'
    assert not dest.exists(), dest
    dest.mkdir()
    for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
        m = json.loads((BUILD / profile / 'manifest.json').read_text('utf8'))
        assert all(sha(ROOT / n) == h for n, h in m['source_inventory'].items())
        assert all(sha(BUILD / profile / n) == h for n, h in m['artifacts'].items())
        for p in (BUILD / profile).iterdir():
            if p.is_file():
                copy(p, dest / '固件' / profile / p.name)
        log = ROOT / '.codex-tmp/restart_guard_v1060_v1243_20261112' / profile / 'build316.log'
        copy(log, dest / '固件' / profile / 'build316_inherited.log')
    for name in m['changed_sources']:
        copy(ROOT / name, dest / '修改源码' / name)
    for p in monitor.rglob('*'):
        if p.is_file():
            copy(p, dest / '监控软件' / p.relative_to(monitor))
    for p in EVIDENCE.rglob('*'):
        if p.is_file():
            copy(p, dest / '离线验证证据' / p.relative_to(EVIDENCE))
    for name in ('build_ambient_scope_v1061_20261112.py', 'test_ambient_scope_arm_20261112.py',
                 'regress_ambient_scope_preservation_20261112.py', 'test_paused_bench_predicates_20261112.py',
                 'bench_remaining_defrost_matrix_20261111.py', 'bench_b04_ambient_20261111.py',
                 'bench_contact_inputs_20261111.py', 'full_queue_contact_inputs_20261112.py',
                 'package_ambient_scope_20261112.py'):
        copy(ROOT / 'tools' / name, dest / '验证脚本' / name)
    copy(ROOT / '环境联锁修复与明日复测_20261112.md', dest / '环境联锁修复与明日复测_20261112.md')
    copy(BUILD / 'change_scope_verification.json', dest / '离线验证证据/change_scope_verification.json')
    metadata = dict(date='2026-11-12', firmware={'330': '10.61', '316': '12.43'},
                    monitor=smoke['version'], flashed=False, hardware_tested=False,
                    bench_paused=True, outdoor_artifacts_byte_identical=True,
                    source_inventory_count=294, new_changed_sources=m['new_changed_sources'],
                    ARM_checks=1012, predicate_checks=26, monitor_checks=354,
                    production_timing_accepted=False, remaining_batches=17,
                    limited_items=83, formal_timing_unmeasured_items=28,
                    two_hour_soak_unexecuted=True, monitor_archive=monitor_zip,
                    validation_scripts_require_current_workspace=True)
    (dest / 'release_manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    result = dict(release=archive(dest), monitor=monitor_zip, metadata=metadata)
    (BUILD / 'package_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
