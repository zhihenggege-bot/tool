"""Authorized BENCH to PRODUCTION transition, backups and full image readback."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import sys
import time
import traceback

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'psc330_monitor_tool/psc330_monitor'))
from app import ModbusRtuClient, DEFAULT_BAUD
from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
from verify_board_flash_vs_hex import parse_hex, blocks_of
from elftools.elf.elffile import ELFFile

D = R / '测试证据/切换正式时序_20261118'
I = R / '.codex-tmp/local_remote_v1064_20261117'
O = R / '.codex-tmp/vfd_unload_min30_v1063_v1246_20261117'
BOARDS = (
    ('316_WJ1', '56FF6E065067545548562587', 'stm32f103rc', 0x414, 256*1024, 48*1024, O, 'PSC316_V12.46'),
    ('316_WJ2', '30FF71064E4B323247481843', 'stm32f103rc', 0x414, 256*1024, 48*1024, O, 'PSC316_V12.46'),
    ('330', '50FF73067289515145451367', 'stm32f407ze', 0x413, 512*1024, 128*1024, I, 'PSC330_V10.64'),
)
EXPECTED = [330,10,64,2026,11,17,316,12,46,2026,11,17,316,12,46,2026,11,17]
BLOCKS = ((0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2),(1319,26),(1388,12),(1830,96),(2680,98))
D.mkdir(exist_ok=True)
P = D / 'deployment.json'
q = dict(started='', authorization='把模式调整为正式模式', profile='PRODUCTION', boards=[], passed=False)


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='milliseconds')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save():
    temp=P.with_suffix('.tmp')
    temp.write_text(json.dumps(q,ensure_ascii=False,indent=2),'utf8');temp.replace(P)


def client():
    c=ModbusRtuClient();c.open('COM6',DEFAULT_BAUD);return c


def snap(c):
    return {str(a):c.read_holding_registers(1,a,n) for a,n in ((2622,18),(1298,2),(700,15),(163,4),
        (398,1),(1352,1),(1388,1),(814,8),(1366,8),(914,10),(594,33),(1555,2),(1625,2),(1300,1))}


def stopped(s):
    return s['700'][9]==0 and s['398']==[0] and not any(s['814']+s['1366']+s['914']+s['1555']+s['1625'])


def config(c):
    return {str(a+i):v for a,n in BLOCKS for i,v in enumerate(c.read_holding_registers(1,a,n))}


def verify(t,path):
    m=parse_hex(path)
    for lo,hi in blocks_of(m):
        for a in range(lo,hi,4096):
            n=min(4096,hi-a)
            assert bytes(t.read_memory_block8(a,n))==bytes(m[a+i] for i in range(n)),(path.name,hex(a))
    return len(m)


def symbols(path):
    with path.open('rb') as f:
        elf=ELFFile(f)
        return {s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name}


def runtime(t,path):
    sy=symbols(path)
    return dict(recovery=t.read16(sy['Parameter']+1298*2), profile=t.read16(sy['Parameter']+1299*2),
                minimum_stop=t.read16(sy['Parameter_min']+42*2),minimum_run=t.read16(sy['Parameter_min']+43*2))


def main():
    assert not P.exists(),'Preserve existing deployment'
    q['started']=now()
    m=json.loads((I/'PRODUCTION/manifest.json').read_text('utf8'))
    assert all(sha(R/n)==h for n,h in m['source_inventory'].items())
    q['source_inventory']=m['source_inventory']
    for directory in (I/'PRODUCTION',O/'PRODUCTION'):
        manifest=json.loads((directory/'manifest.json').read_text('utf8'))
        assert all(sha(directory/n)==h for n,h in manifest['artifacts'].items())
    old_o=json.loads((O/'PRODUCTION/manifest.json').read_text('utf8'))
    assert all(sha(R/n)==h for n,h in old_o['source_inventory'].items() if n.startswith('PSC316'))
    c=client()
    try:
        q['before']=snap(c)
        assert q['before']['2622']==EXPECTED and q['before']['1298']==[3,15107]
        assert stopped(q['before']) and not any(q['before']['594']) and q['before']['1300']==[0]
        assert q['before']['163'][0]==1 and q['before']['1352']==[0] and q['before']['1388']==[0]
        q['config_before']=config(c)
        save()
    finally:c.close()
    # Audit every old image before the first programming operation.
    for label,uid,target,device,flash_size,ram_size,base,stem in BOARDS:
        with ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
            options={'connect_mode':'attach','resume_on_disconnect':False,'frequency':1000000}) as ss:
            t=ss.target
            assert t.read32(0xE0042000)&0xfff==device
            count=verify(t,base/'BENCH_ONLY_3S'/f'{stem}_BENCH_ONLY_3S.hex')
            q['boards'].append(dict(board=label,probe=uid,old_verified_bytes=count,programmed=False))
            save()
    for row,board in zip(q['boards'],BOARDS):
        label,uid,target,device,flash_size,ram_size,base,stem=board
        with ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
            options={'connect_mode':'attach','resume_on_disconnect':False,'frequency':1000000}) as ss:
            t=ss.target
            t.halt();debug=t.read32(0xE0042008);started=False;completed=False
            try:
                for suffix,a,n in (('flash',0x08000000,flash_size),('sram',0x20000000,ram_size)):
                    dest=D/f'{label}_before_{suffix}.bin'
                    assert not dest.exists()
                    dest.write_bytes(bytes(t.read_memory_block8(a,n)))
                    row[suffix+'_backup']=dict(file=dest.name,bytes=n,sha256=sha(dest))
                save()
                image=base/'PRODUCTION'/f'{stem}_PRODUCTION.hex'
                row['image']=str(image.relative_to(R));row['image_sha256']=sha(image)
                t.write32(0xE0042008,debug|0x1800);t.reset_and_halt()
                t.write32(0xE0042008,t.read32(0xE0042008)|0x1800)
                started=True;row['programming_started']=now();save()
                FileProgrammer(ss,chip_erase='sector',trust_crc=False).program(str(image))
                row['programmed']=True;row['verified_bytes']=verify(t,image)
                row['flash_verified']=True;completed=True;save()
            finally:
                if completed:t.write32(0xE0042008,debug);t.reset()
                elif not started:t.write32(0xE0042008,debug);t.resume()
                else:t.halt();row['recovery_required']=True;save()
        print('PRODUCTION FLASH VERIFIED',label,row['verified_bytes'],flush=True)
    c=client()
    try:
        deadline=time.monotonic()+100
        while True:
            try:
                s=snap(c)
                if s['2622']==EXPECTED and s['1298']==[300,0] and stopped(s) and s['700'][0]!=10:
                    if all(c.read_holding_registers(1,int(a),1)[0]==v for a,v in q['config_before'].items() if 2680<=int(a)<2778):break
            except Exception:pass
            assert time.monotonic()<deadline,'boot/mirror refill timeout'
            time.sleep(.5)
        q['after']=snap(c);q['config_after']=config(c)
        q['changes']={a:[v,q['config_after'][a]] for a,v in q['config_before'].items() if q['config_after'][a]!=v}
        allowed={42,43,1298,1299,167,373,1875,1923}
        q['unexpected_changes']={a:v for a,v in q['changes'].items() if int(a) not in allowed}
        assert not q['unexpected_changes'],q['unexpected_changes']
        assert q['after']['163']==q['before']['163'] and q['after']['1352']==[0]
        assert not any(q['after']['594']) and stopped(q['after'])
        assert int(q['config_after']['42'])>=120 and int(q['config_after']['43'])>=180
        assert q['config_after']['1341']==q['config_before']['1341']==30
        save()
    finally:c.close()
    # Bind profile and compiled minima directly to each board, not only 330 mirrors.
    for row,board in zip(q['boards'],BOARDS):
        label,uid,target,device,flash_size,ram_size,base,stem=board
        with ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
            options={'connect_mode':'attach','resume_on_disconnect':False,'frequency':1000000}) as ss:
            t=ss.target
            row['final_verified_bytes']=verify(t,base/'PRODUCTION'/f'{stem}_PRODUCTION.hex')
            row['runtime_profile']=runtime(t,base/'PRODUCTION'/f'{stem}_PRODUCTION.axf')
            assert row['runtime_profile']==dict(recovery=300,profile=0,minimum_stop=120,minimum_run=180),row
            save()
    q.update(passed=True,finished=now());save()
    print('DEPLOYMENT PASS',json.dumps(q['changes']),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException:
        q.update(error=traceback.format_exc(),finished=now());save();raise
