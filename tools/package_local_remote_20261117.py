"""Package V10.64 evidence and monitor 17c with verified archive contents."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile

R = Path(__file__).resolve().parents[1]
S = R / 'psc330_monitor_tool/psc330_monitor'
E = R / '测试证据/本地远程X02_20261117'
B = R / '.codex-tmp/monitor_local_remote_20261117c'
D = R / '监控工具_FFP-2026.11.17c'
F = R / '固件_330V10.64_本地远程X02_20261117'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def copy(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def archive(folder):
    files = sorted(p for p in folder.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.txt')
    (folder / 'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {p.relative_to(folder).as_posix()}\n' for p in files), 'utf8')
    target = folder.with_suffix('.zip') if folder == F else R / (folder.name + '.zip')
    # Folder names include a version decimal; never drop that suffix.
    target = R / (folder.name + '.zip')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files + [folder / 'SHA256SUMS.txt']:
            z.write(p, p.relative_to(folder).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for p in files + [folder / 'SHA256SUMS.txt']:
            assert hashlib.sha256(z.read(p.relative_to(folder).as_posix())).hexdigest() == sha(p)
    return dict(path=target.name, sha256=sha(target), bytes=target.stat().st_size, archive_verified=True)


def main():
    for name in ('deployment.json', 'board_tests.json', 'monitor_gui.json', 'monitor_live.json'):
        assert json.loads((E / name).read_text('utf8'))['passed'], name
    smoke = json.loads((E / 'monitor_exe_smoke.json').read_text('utf8'))
    assert smoke['version'] == 'FFP-2026.11.17c' and smoke['gui_created'] and not smoke['serial_opened']
    regression = json.loads((E / 'monitor_fault_regression.json').read_text('utf8'))
    assert regression['total'] == regression['passed'] == 354
    assert regression['source_sha256'] == sha(S / 'app.py')
    toc = (B / 'build/PSC330_PSC316_Monitor/Analysis-00.toc').read_text('utf8')
    assert all(name in toc for name in ('control_source', 'pt_tables', 'serial.serialwin32'))
    unit = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', 'test_control_source'], cwd=S, capture_output=True, text=True)
    assert unit.returncode == 0, unit.stderr
    (E / 'monitor_control_unit_tests.json').write_text(json.dumps(dict(passed=True, tests=10, hardware_access=False,
        result=unit.stderr, source_sha256=sha(S / 'control_source.py')), ensure_ascii=False, indent=2), 'utf8')
    D.mkdir(exist_ok=True)
    copy(B / 'dist/PSC330_PSC316_Monitor.exe', D / 'PSC330_PSC316_Monitor.exe')
    for name in ('app.py', 'control_source.py', 'pt_tables.py', 'test_control_source.py', 'test_fault_summary.py', 'PSC330_PSC316_Monitor.spec', 'README.md', 'run_psc330_monitor.bat'):
        copy(S / name, D / 'Python源码' / name)
    copy(S / 'README.md', D / '使用说明.md')
    (D / '使用说明.txt').write_text(
        'PSC330/PSC316 监控工具 FFP-2026.11.17c，配套330 V10.64。\n'
        '双击PSC330_PSC316_Monitor.exe，无需安装Python。\n'
        '通信与机组控制页：选择本地/远程并应用；本地下另选手动/定时。\n'
        '本地手动：163=0、165=0，由398启停，X02无效。\n'
        '本地定时：163=0、165=1，由1388目标启停；星期/时间在HMI周计划中设置并启用。\n'
        '远程：163=1，X02保持接点接通开机、断开正常停机，手动/定时命令不接管。\n'
        '应用手动/定时需先正常停机；来源切换按原顺序正常停机。\n'
        '监控软件的1388按钮用于联调，不执行周计划；HMI计划运行时不要并行联调目标。\n'
        '共享参数独立页、单项写入修复保留，升级软件不自动修改设备保存参数。\n'
        '台架已烧录330 V10.64 BENCH_ONLY_3S，两台316 V12.46保持原版；六组通风软件反馈验收通过。\n'
        '真实X02接点、实体端子输出、HMI工程下载和正式秒数仍需现场验收。\n', 'utf8')
    for name in ('monitor_gui.json', 'monitor_live.json', 'monitor_live_precondition_running.json', 'monitor_fault_regression.json', 'monitor_control_unit_tests.json', 'monitor_exe_smoke.json'):
        copy(E / name, D / '验证记录' / name)
    copy(R / '本地远程X02修改与验证_20261117.md', F / '本地远程X02修改与验证_20261117.md')
    for name in ('deployment.json', 'board_tests.json', 'events.jsonl'):
        copy(E / name, F / '台架证据' / name)
    for name in ('local_remote_bench_20261117.py', 'check_monitor_local_remote_20261117.py'):
        copy(R / 'tools' / name, F / 'tools' / name)
    q = dict(monitor=archive(D), firmware=archive(F), exe_sha256=sha(D / 'PSC330_PSC316_Monitor.exe'))
    (E / 'package_verification.json').write_text(json.dumps(q, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(q, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
