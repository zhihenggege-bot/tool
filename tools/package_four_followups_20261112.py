"""Create a hash-verified release after the scoped bench is restored."""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

R=Path(__file__).resolve().parents[1]
E=R/'测试证据/四项复核_20261112'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build',default='.codex-tmp/vfd_scale_v1242_20261112')
    parser.add_argument('--audit',required=True)
    args=parser.parse_args();build=R/args.build
    audit=json.loads((R/args.audit).read_text('utf8'))
    assert audit['verified'] and audit['artifact_hashes_match']
    assert not audit['restoration_mismatches']
    assert audit['snapshot']['state'][9]==0
    monitor=json.loads((R/'.codex-tmp/vfd_scale_v1242_20261112/monitor_package_verification.json').read_text('utf8'))
    assert monitor['archive_verified'] and monitor['checks']==354
    assert sha(R/'psc330_monitor_tool/psc330_monitor/app.py')==monitor['source_sha256']
    manifest=json.loads((build/'BENCH_ONLY_3S/manifest.json').read_text('utf8'))
    iv=manifest.get('indoor_version','10.59');ov=manifest['outdoor_version']
    assert audit['versions'][:3]==[330,10,int(iv.split('.')[1])]
    assert audit['versions'][6:9]==[316,12,int(ov.split('.')[1])]
    dest=R/f'发布包_330V{iv}_316V{ov}_20261112'
    assert not dest.exists(),'Keep previous packages immutable'
    dest.mkdir()
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        m=json.loads((build/profile/'manifest.json').read_text('utf8'))
        assert len(m['source_inventory'])==294
        assert all(sha(R/p)==h for p,h in m['source_inventory'].items())
        assert all(sha(build/profile/p)==h for p,h in m['artifacts'].items())
        for p in (build/profile).iterdir():
            if p.is_file():copy(p,dest/'固件'/profile/p.name)
        for model in ('330','316'):
            log=build/profile/f'build{model}.log'
            if not log.exists():log=R/'.codex-tmp/issuefix_v1059_v1241_20261111'/profile/f'build{model}.log'
            assert '0 Error(s), 0 Warning(s)' in log.read_text('utf-8-sig')
            copy(log,dest/'固件'/profile/f'build{model}.log')
    for p in manifest['changed_sources']:copy(R/p,dest/'修改源码'/p)
    for name in ('build_restart_guard_v1060_20261112.py','test_restart_guard_arm_20261112.py',
        'test_typeII_recovery_arm_20261112.py','test_adc_fixture_scale_20261112.py',
        'test_adc_robust_fixture_arm_20261112.py','test_typeII_independent_OR_arm_20261112.py','regress_restart_guard_preservation_20261112.py',
        'bench_typeII_recovery_fix_20261112.py','bench_typeII_OR_robust_20261112.py',
        'bench_typeII_OR_gateway_20261112.py',
        'bench_low_pressure_stable_20261112.py','bench_restart_diagnostics_20261112.py',
        'bench_restart_fix_20261112.py','joint_v1060_context_20261112.py',
        'analyze_restart_diagnostics_20261112.py','report_four_followups_20261112.py'):
        copy(R/'tools'/name,dest/'验证脚本'/name)
    for p in (R/'监控工具_FFP-2026.11.12a').rglob('*'):
        if p.is_file():copy(p,dest/'监控软件'/p.relative_to(R/'监控工具_FFP-2026.11.12a'))
    for p in E.rglob('*'):
        if p.is_file():copy(p,dest/'验证证据'/p.relative_to(E))
    report=R/'四项复核结果_20261112.md';copy(report,dest/report.name)
    copy(R/args.audit,dest/'最终恢复审计.json')
    metadata=dict(date='2026-11-12',firmware={'330':iv,'316':ov},monitor=monitor['version'],
        source_inventory_count=294,changed_sources=manifest['changed_sources'],
        bench_evidence='See per-case records; no blanket claim of full acceptance',
        terminal_voltage_measured=False,production_timing_accepted=False,
        limited_items=83,formal_timing_unmeasured_items=28,
        whole_queue_and_2h_soak_paused=True,final_audit=args.audit,
        monitor_checks=354,monitor_exe_sha256=monitor['exe_sha256'])
    (dest/'release_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')
    (dest/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(dest).as_posix()+'\n'
        for p in sorted(dest.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt'),encoding='utf8')
    archive=R/(dest.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(dest.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(dest).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for p in dest.rglob('*'):
            if p.is_file():assert hashlib.sha256(z.read(p.relative_to(dest).as_posix())).hexdigest()==sha(p)
    q=dict(package=str(archive.relative_to(R)),sha256=sha(archive),archive_verified=True,
           final_restore_verified=True,metadata=metadata)
    (build/'package_verification.json').write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(q,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
