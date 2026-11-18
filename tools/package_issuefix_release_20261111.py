"""Package verified firmware/monitor without flashing or touching bench state."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'.codex-tmp/issuefix_v1059_v1241_20261111'
EVIDENCE=ROOT/'测试证据/修复回归_20261111'
RELEASE=ROOT/'发布包_330V10.59_316V12.41_20261111'
MONITOR=ROOT/'psc330_monitor_tool/psc330_monitor'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)


def archive(folder,destination):
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(folder).as_posix())
    with zipfile.ZipFile(destination) as z:
        assert z.testzip() is None
        for p in sorted(folder.rglob('*')):
            if p.is_file():assert hashlib.sha256(z.read(p.relative_to(folder).as_posix())).hexdigest()==sha(p)


def main():
    suites=('focused_arm','shared','protection','lifecycle','comm','fan_threshold','monitor_tests')
    stats={}
    for suite in suites:
        name=suite+('_results.json' if suite!='monitor_tests' else '.json')
        r=json.loads((EVIDENCE/name).read_text('utf8'))
        assert r['total']==r['passed'] and r['total']>0,(suite,r)
        stats[suite]={'passed':r['passed'],'total':r['total']}
    assert sum(v['passed'] for k,v in stats.items() if k!='monitor_tests')==1290
    assert stats['monitor_tests']['passed']==354
    assert json.loads((EVIDENCE/'monitor_tests.json').read_text('utf8'))['source_sha256']==sha(MONITOR/'app.py')
    smoke=json.loads((BUILD/'monitor_exe_smoke.json').read_text('utf8'))
    assert smoke['version']=='FFP-2026.11.11a' and smoke['gui_created'] and not smoke['serial_opened']
    assert 'pt_tables' in (BUILD/'pyinstaller/PSC330_PSC316_Monitor/Analysis-00.toc').read_text('utf8')
    identity=json.loads((BUILD/'final_firmware_identity.json').read_text('utf8'))
    assert identity['source_inventory_count']==294 and identity['pause_retained'] and identity['queue_unchanged']
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        m=json.loads((BUILD/profile/'manifest.json').read_text('utf8'))
        assert all(sha(ROOT/p)==h for p,h in m['source_inventory'].items())
        assert all(sha(BUILD/profile/p)==h for p,h in m['artifacts'].items())
        for model in ('330','316'):
            assert '0 Error(s), 0 Warning(s)' in (BUILD/profile/f'build{model}.log').read_text('utf-8-sig')
        for p in (BUILD/profile).iterdir():
            if p.is_file():copy(p,RELEASE/'固件'/profile/p.name)
    for path in m['changed_sources']:copy(ROOT/path,RELEASE/'修改源码'/path)
    for name in ('app.py','pt_tables.py','PSC330_PSC316_Monitor.spec','README.md','test_fault_summary.py'):
        copy(MONITOR/name,RELEASE/'监控软件/Python源码'/name)
    (RELEASE/'监控软件/使用说明.txt').write_text(
        'PSC330 / PSC316 监控工具 FFP-2026.11.11a\n'
        '双击PSC330_PSC316_Monitor.exe，无需安装Python。仅经330读取/设置外机。\n'
        '配套330 V10.59 / 316 V12.41；运行策略及HMI兼容事项见包内交付说明。\n'
        '新增中文故障摘要；逐条与ERR不一致、数据未读全或过期将单独提示。\n',encoding='utf8')
    report=ROOT/'修复交付说明_330V10.59_316V12.41_20261111.md'
    copy(report,RELEASE/report.name)
    for p in EVIDENCE.rglob('*'):
        if p.is_file():copy(p,RELEASE/'验证证据'/p.relative_to(EVIDENCE))
    for name in ('monitor_exe_smoke.json','monitor_source_smoke.json','final_firmware_identity.json','source_before.json','source_after.json'):
        copy(BUILD/name,RELEASE/'验证证据'/name)
    metadata=dict(date='2026-11-11',firmware={'330':'10.59','316':'12.41'},monitor=smoke['version'],
        hardware_tested=False,flashed=False,bench_paused=True,source_inventory_count=294,
        changed_firmware_sources=m['changed_sources'],checks=stats,
        monitor_source_sha256=sha(MONITOR/'app.py'),monitor_exe_sha256=sha(RELEASE/'监控软件/PSC330_PSC316_Monitor.exe'))
    (RELEASE/'release_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n','utf8')
    lines=[sha(p)+'  '+p.relative_to(RELEASE).as_posix() for p in sorted(RELEASE.rglob('*'))
           if p.is_file() and p.name!='SHA256SUMS.txt']
    (RELEASE/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n','utf8')
    monitor_zip=ROOT/'PSC330_PSC316_Monitor_FFP-2026.11.11a.zip'
    full_zip=ROOT/(RELEASE.name+'.zip')
    archive(RELEASE/'监控软件',monitor_zip)
    archive(RELEASE,full_zip)
    checksums={p.name:sha(p) for p in (full_zip,monitor_zip)}
    (ROOT/'发布包_20261111_SHA256.txt').write_text(''.join(h+'  '+n+'\n' for n,h in checksums.items()),'utf8')
    verification=dict(release=str(RELEASE.relative_to(ROOT)),zip_verified=True,
        package_sha256=checksums,files=len(lines)+1,checks=stats,
        hardware_access=False,flashed=False,monitor_smoke=smoke)
    (BUILD/'package_verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(verification,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
