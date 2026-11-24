"""Authorized 330-only DA8 manual firmware deployment, with immutable backups."""
import json
import time
import traceback
from pathlib import Path

import deploy_production_v1064_v1246_20261118 as d
from build_normal_stop_v1070_20261119 import inventory

R = Path(__file__).resolve().parents[1]
DAY = R / '测试证据/DA8仅手动及防冻归属_V1074_20261124'
OUT = R / '.codex-tmp/da8_water_valve_v1074_20261124/PRODUCTION'
OLD = R / '.codex-tmp/cooling_ambient_v1073_v1256_20261123/PRODUCTION'
NEW = OUT / 'PSC330_V10.74_PRODUCTION.hex'
BOARDS = (
    ('316_WJ1', '56FF6E065067545548562587', 'stm32f103rc', 0x414, 262144, 49152, OLD/'PSC316_V12.56_PRODUCTION.hex'),
    ('316_WJ2', '30FF71064E4B323247481843', 'stm32f103rc', 0x414, 262144, 49152, OLD/'PSC316_V12.56_PRODUCTION.hex'),
    ('330', '50FF73067289515145451367', 'stm32f407ze', 0x413, 524288, 131072, OLD/'PSC330_V10.73_PRODUCTION.hex'),
)
EXPECTED = [330,10,74,2026,11,24,316,12,56,2026,11,23,316,12,56,2026,11,23]


def dump(path, data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf8')
    temp.replace(path)


def main():
    path=DAY/'deployment.json'
    assert not path.exists(), 'Preserve previous deployment evidence'
    manifest=json.loads((OUT/'manifest.json').read_text('utf8'))
    assert inventory()==manifest['source_inventory']
    assert all(d.sha(OUT/n)==v for n,v in manifest['artifacts'].items())
    arm=json.loads((DAY/'manual_ARM_regression.json').read_text('utf8'))
    assert arm['passed']
    q=dict(started=d.now(), authorization='烧录测试 DA8仅手动及水阀防冻最小开度',
           passed=False, boards=[], source_inventory=manifest['source_inventory'])
    def save():dump(path,q)
    try:
        c=d.client()
        try:
            q['before']=d.snap(c)
            assert d.stopped(q['before']) and not any(q['before']['594'])
            assert q['before']['2622']==[330,10,73,2026,11,20]+EXPECTED[6:]
            assert q['before']['1300']==[0] and q['before']['1298']==[300,0]
            q['config_before']=d.config(c)
        finally:c.close()
        save()
        for label,uid,target,device,flash,ram,image in BOARDS:
            with d.ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
                    options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
                assert ss.target.read32(0xE0042000)&0xfff==device
                q['boards'].append(dict(board=label, probe=uid,
                    old_image=str(image.relative_to(R)), old_verified_bytes=d.verify(ss.target,image), programmed=False))
                save()
        label,uid,target,device,flash,ram,old=BOARDS[2]
        with d.ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
                options={'connect_mode':'attach','resume_on_disconnect':False,'frequency':1000000}) as ss:
            t=ss.target;t.halt();debug=t.read32(0xE0042008);started=False;complete=False
            try:
                for suffix,addr,size in (('flash',0x08000000,flash),('sram',0x20000000,ram)):
                    backup=DAY/f'330_before_{suffix}.bin';assert not backup.exists()
                    backup.write_bytes(bytes(t.read_memory_block8(addr,size)))
                    q[suffix+'_backup']=dict(file=backup.name,bytes=size,sha256=d.sha(backup))
                save();t.write32(0xE0042008,debug|0x1800);t.reset_and_halt()
                t.write32(0xE0042008,t.read32(0xE0042008)|0x1800)
                started=True;q['programming_started']=d.now();save()
                d.FileProgrammer(ss,chip_erase='sector',trust_crc=False).program(str(NEW))
                q['boards'][2].update(programmed=True,verified_bytes=d.verify(t,NEW),sha256=d.sha(NEW))
                complete=True;save()
            finally:
                if complete:t.write32(0xE0042008,debug);t.reset()
                elif not started:t.write32(0xE0042008,debug);t.resume()
                else:t.halt();q['recovery_required']=True;save()
        c=d.client()
        try:
            start=time.monotonic()
            while True:
                try:
                    s=d.snap(c)
                    q.setdefault('boot_samples',[]).append(dict(at=d.now(),snapshot=s));save()
                    if s['2622']==EXPECTED and d.stopped(s) and not any(s['594']) and s['1298']==[300,0]:break
                except Exception as exc:
                    q.setdefault('boot_errors',[]).append(str(exc));save()
                assert time.monotonic()-start<150, 'Postboot readiness timeout'
                time.sleep(.5)
            q['after']=s
            ignored={1,167,373,1875,1923,1971,2019,259,1876,1924,1972,2020}
            while True:
                actual=d.config(c)
                mismatch={a:[v,actual[a]] for a,v in q['config_before'].items()
                    if int(a) not in ignored|{245} and actual[a]!=v}
                if not mismatch:break
                q['pending_mismatches']=mismatch;save()
                assert time.monotonic()-start<150, mismatch
                time.sleep(.5)
            q.update(config_after=actual,configuration_mismatches=mismatch,
                intentional_manual_migration={'245':[q['config_before']['245'],actual['245']]})
            assert actual['245']==1 and actual['247']==q['config_before']['247']
        finally:c.close()
        for row,board in zip(q['boards'],BOARDS):
            image=NEW if board[0]=='330' else board[6]
            with d.ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
                    options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
                row['final_verified_bytes']=d.verify(ss.target,image)
                row['runtime_profile']=d.runtime(ss.target,image.with_suffix('.axf'))
                assert row['runtime_profile']==dict(recovery=300,profile=0,minimum_stop=120,minimum_run=180)
                save()
        q.update(passed=True,finished=d.now());save()
        manifest.update(flashed=True,hardware_tested=False,deployment_evidence=str(path.relative_to(R)))
        dump(OUT/'manifest.json',manifest)
        print('DEPLOY PASS: 330 V10.74 PRODUCTION; outdoor V12.56 unchanged; 245 normalized to manual1',flush=True)
    except BaseException:
        q.update(error=traceback.format_exc(),finished=d.now());save();raise


if __name__=='__main__':main()
