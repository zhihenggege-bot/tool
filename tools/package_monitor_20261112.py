"""Package the verified offline monitor; never touches bench devices."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
B = R/'.codex-tmp/vfd_scale_v1242_20261112'
S = R/'psc330_monitor_tool/psc330_monitor'
D = R/'监控工具_FFP-2026.11.12a'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    smoke = json.loads((B/'monitor_exe_smoke.json').read_text('utf8'))
    tests = json.loads((R/'测试证据/四项复核_20261112/monitor_tests.json').read_text('utf8'))
    assert smoke['version'] == tests['version'] == 'FFP-2026.11.12a'
    assert smoke['gui_created'] and not smoke['serial_opened']
    assert tests['passed'] == tests['total'] == 354
    assert tests['source_sha256'] == sha(S/'app.py')
    toc = (B/'pyinstaller/PSC330_PSC316_Monitor/Analysis-00.toc').read_text('utf8')
    assert 'pt_tables' in toc and 'serial.serialwin32' in toc
    D.mkdir(exist_ok=True)
    shutil.copy2(B/'monitor_dist/PSC330_PSC316_Monitor.exe',D/'PSC330_PSC316_Monitor.exe')
    src = D/'Python源码'
    src.mkdir(exist_ok=True)
    for name in ('app.py','pt_tables.py','PSC330_PSC316_Monitor.spec','README.md','test_fault_summary.py'):
        shutil.copy2(S/name,src/name)
    (D/'使用说明.txt').write_text(
        'PSC330 / PSC316 监控工具 FFP-2026.11.12a\n'
        '双击 PSC330_PSC316_Monitor.exe，无需安装 Python。\n'
        '更新外机 DA0 换算说明：316 V12.42 固定 0～10V 对应 0～50Hz。\n'
        '最高频率参数只限制频率目标：30Hz→DA600，40Hz→DA800，50Hz→DA1000。\n'
        '旧316 V12.41及以前的换算可能随最高频率变化，应先核对固件版本。\n'
        'DA回读是软件输出值，不能代替端子电压和实际风机频率测量。\n'
        '本次不改变监控软件通讯、写入和控制行为。\n',encoding='utf8')
    for name in ('monitor_exe_smoke.json',):
        shutil.copy2(B/name,D/name)
    shutil.copy2(R/'测试证据/四项复核_20261112/monitor_tests.json',D/'monitor_tests.json')
    (D/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(D).as_posix()+'\n'
        for p in sorted(D.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt'),encoding='utf8')
    dest = R/(D.name+'.zip')
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(D.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(D).as_posix())
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for p in D.rglob('*'):
            if p.is_file():assert hashlib.sha256(z.read(p.relative_to(D).as_posix())).hexdigest()==sha(p)
    q=dict(version=smoke['version'],zip=str(dest.relative_to(R)),zip_sha256=sha(dest),
        source_sha256=sha(S/'app.py'),exe_sha256=sha(D/'PSC330_PSC316_Monitor.exe'),
        checks=354,gui_smoke=smoke,hardware_access=False,archive_verified=True)
    (B/'monitor_package_verification.json').write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(q,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
