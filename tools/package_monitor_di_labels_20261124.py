"""Package the DI label-only monitor update; never connects to hardware."""
import difflib
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from build_normal_stop_v1070_20261119 import inventory

R=Path(__file__).resolve().parents[1]
B=R/'.codex-tmp/monitor_di_labels_20261124c'
S=R/'psc330_monitor_tool/psc330_monitor'
D=R/'监控工具_FFP-2026.11.24c'
V='FFP-2026.11.24c'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    tests=json.loads((B/'di_checks.json').read_text('utf8'))
    smoke=json.loads((B/'exe_smoke.json').read_text('utf8'))
    assert tests['passed'] and tests['total']==115
    assert tests['version']==smoke['version']==V
    assert smoke['gui_created'] and not smoke['serial_opened']
    assert tests['source_sha256']==sha(S/'app.py')
    firmware=json.loads((R/'.codex-tmp/di_faults_v1076_20261124/PRODUCTION/manifest.json').read_text('utf8'))
    assert inventory()==firmware['source_inventory'],'Firmware must remain unchanged'
    old=(R/'监控工具_FFP-2026.11.24b/Python源码/app.py').read_text('utf8')
    diff=''.join(difflib.unified_diff(old.splitlines(True),(S/'app.py').read_text('utf8').splitlines(True),
        fromfile='app.py FFP-2026.11.24b',tofile='app.py '+V))
    (B/'label_changes.diff').write_text(diff,'utf8')
    D.mkdir(exist_ok=True)
    shutil.copy2(B/'dist/PSC330_PSC316_Monitor.exe',D/'PSC330_PSC316_Monitor.exe')
    src=D/'Python源码';src.mkdir(exist_ok=True)
    for name in ('app.py','pt_tables.py','README.md','PSC330_PSC316_Monitor.spec','test_di_protections.py'):
        shutil.copy2(S/name,src/name)
    notes=(
        'PSC330 / PSC316 监控工具 '+V+'\n'
        '双击PSC330_PSC316_Monitor.exe，无需Python，无需重新烧录固件。\n'
        '故障名称标注对应X编号；605说明列明确它是多路DI综合保护。\n'
        '605汇总X01消防、X04风阀联锁、X11排风机过载、X12回风机过载、X13漏水。\n'
        '对应独立故障分别是960、962、956、958、964；整机总报警为861。\n'
        'DI保护明细顶部也列出605的全部来源。\n'
        '960/962/964说明列改为具体X点、滤波后输入与复位说明，不再常驻版本要求文字。\n'
        '低于330 V10.76或版本未知时仍显示版本不支持，不把未实现反馈当无故障。\n'
        '本次只改显示，固件、设备参数、通讯与控制行为均未修改。\n'
        '115项DI显示检查与打包EXE启动检查通过。\n')
    (D/'使用说明.txt').write_text(notes,'utf8')
    for name in ('di_checks.json','exe_smoke.json'):
        shutil.copy2(B/name,D/name)
    (D/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(D).as_posix()+'\n'
        for p in sorted(D.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt'),'utf8')
    dest=R/(D.name+'.zip')
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(D.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(D).as_posix())
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for p in D.rglob('*'):
            if p.is_file():assert hashlib.sha256(z.read(p.relative_to(D).as_posix())).hexdigest()==sha(p)
    report=dict(version=V,passed=True,checks=115,exe_smoke=True,firmware_unchanged=True,
        hardware_access=False,source_sha256=sha(S/'app.py'),exe_sha256=sha(D/'PSC330_PSC316_Monitor.exe'),
        zip_sha256=sha(dest),archive_verified=True)
    (B/'package_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    evidence=S/'verification'/V;evidence.mkdir(parents=True,exist_ok=True)
    for name in ('di_checks.json','exe_smoke.json','package_verification.json','label_changes.diff'):
        shutil.copy2(B/name,evidence/name)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
