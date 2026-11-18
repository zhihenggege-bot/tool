"""Authorized stopped330 upgrade with backups and full HEX readback; no tests."""
import base64
import hashlib
import json
import time
import traceback
from pathlib import Path
import full_queue_context_20261113 as ctx
from verify_board_flash_vs_hex import parse_hex, blocks_of
from pyocd.flash.file_programmer import FileProgrammer


def main():
    path = ctx.DAY / 'deployment.json'
    assert not path.exists(), 'Keep prior flash journal; inspect before retry'
    m = json.loads((ctx.I / 'manifest.json').read_text('utf8'))
    assert all(hashlib.sha256((ctx.R / n).read_bytes()).hexdigest()==h for n,h in m['source_inventory'].items())
    assert all(hashlib.sha256((ctx.I / n).read_bytes()).hexdigest()==h for n,h in m['artifacts'].items())
    q = dict(started=ctx.now(), authorization='接着测试！认真烧录测试！',
             profile='BENCH_ONLY_3S', source_inventory=m['source_inventory'], artifacts=m['artifacts'], boards=[])
    c = ctx.runtime.client()
    try:
        q['versions_before'] = c.read_holding_registers(1,2622,18)
        assert q['versions_before'] == [330,10,60,2026,11,12,316,12,43,2026,11,12,316,12,43,2026,11,12]
        q['snapshot_before'] = ctx.runtime.snap(c)
        assert c.read_holding_registers(1,398,1)==[0]
        assert q['snapshot_before']['state'][9]==0 and ctx.loads_off(q['snapshot_before'])
        q['config_before'] = {}
        for a,n in [(0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2),(1319,26),(1389,11),(1830,96),(2680,98)]:
            q['config_before'].update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        probes = {p.unique_id for p in ctx.ConnectHelper.get_all_connected_probes(blocking=False)}
        assert {b[1] for b in ctx.BOARDS}.issubset(probes)
        ctx.dump(path,q)
    finally:
        c.close()
    for board in ctx.BOARDS:
        label,uid,target,device,flash_size,ram_size,stem = board
        entry = dict(board=label,started=ctx.now(),programmed=False)
        q['boards'].append(entry)
        with ctx.ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target
            assert t.read32(0xE0042000)&0xfff==device
            # Only330 changed. Verify316 images in place without resetting them.
            if label=='330':
                t.halt()
                old_debug=t.read32(0xE0042008)
                programmed=False
                try:
                    for suffix,address,size in [('flash',0x08000000,flash_size),('sram',0x20000000,ram_size)]:
                        raw=bytes(t.read_memory_block8(address,size))
                        backup=ctx.DAY/f'{label}_before_v1061_{suffix}.bin.base64'
                        assert not backup.exists()
                        backup.write_text(base64.b64encode(raw).decode('ascii'),encoding='ascii')
                        assert base64.b64decode(backup.read_bytes())==raw
                        entry[suffix+'_backup']=dict(path=backup.name,bytes=size,sha256=hashlib.sha256(raw).hexdigest())
                    ctx.dump(path,q)
                    t.write32(0xE0042008,old_debug|0x1800)
                    t.reset_and_halt();t.write32(0xE0042008,t.read32(0xE0042008)|0x1800)
                    FileProgrammer(ss,chip_erase='sector',trust_crc=False).program(str(ctx.I/(stem+'.hex')))
                    programmed=True;entry['programmed']=True
                    mem=parse_hex(ctx.I/(stem+'.hex'))
                    for lo,hi in blocks_of(mem):
                        for a in range(lo,hi,4096):
                            n=min(4096,hi-a)
                            assert bytes(t.read_memory_block8(a,n))==bytes(mem[a+i] for i in range(n)),(label,hex(a))
                    entry['verified_bytes']=len(mem)
                finally:
                    t.write32(0xE0042008,old_debug)
                    if programmed:t.reset()
                    else:t.resume()
            else:
                sy=ctx.precondition.symbols(board)
                p=sy['Parameter'][0]
                entry['before_status']={'alarms':[t.read16(p+2*a) for a in range(600,628)],
                    'output':list(t.read_memory_block8(*sy['output'])),
                    'settings':[t.read16(p+2*a) for a in range(165,207)]}
                assert not any(entry['before_status']['output'][i] for i in (0,1,2,3,4,5,7))
                mem=parse_hex(ctx.I/(stem+'.hex'))
                for lo,hi in blocks_of(mem):
                    for a in range(lo,hi,4096):
                        n=min(4096,hi-a)
                        assert bytes(t.read_memory_block8(a,n))==bytes(mem[a+i] for i in range(n)),(label,hex(a))
                entry['verified_bytes']=len(mem)
            entry.update(flash_verified=True,finished=ctx.now())
            ctx.dump(path,q)
        print('PROGRAM/READBACK VERIFIED',label,entry['programmed'],entry['verified_bytes'],flush=True)
    c=ctx.runtime.client()
    try:
        end=time.monotonic()+90
        while True:
            try:v=c.read_holding_registers(1,2622,18)
            except Exception:v=[]
            if v==ctx.runtime.EXPECTED:break
            assert time.monotonic()<end,v
            time.sleep(.5)
        q['versions_after']=v
        # Wait for EEPROM configuration load without changing saved settings.
        sy=ctx.runtime.axf_symbols()
        with ctx.ConnectHelper.session_with_chosen_probe(unique_id=ctx.BOARDS[2][1],target_override=ctx.BOARDS[2][2],
             options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            while True:
                if ss.target.read8(sy['IndoorAiCfgLoaded'][0])==1 and ss.target.read8(sy['eepromtt'][0])==3 and ss.target.read32(sy['Systick_1ms'][0])>=21000:break
                assert time.monotonic()<end
                time.sleep(.3)
        q['config_after']={a:c.read_holding_registers(1,int(a),1)[0] for a in q['config_before']}
        q['configuration_changes']={a:[v,q['config_after'][a]] for a,v in q['config_before'].items()
            if int(a) not in (167,373) and q['config_after'][a]!=v}
        assert not q['configuration_changes'],q['configuration_changes']
        q['snapshot_after']=ctx.runtime.snap(c)
        q['profile_after']=c.read_holding_registers(1,1298,2)
        assert q['profile_after']==[3,15107]
        assert q['snapshot_after']['state'][9]==0 and ctx.loads_off(q['snapshot_after'])
        q.update(verified=True,finished=ctx.now())
        ctx.dump(path,q)
    finally:c.close()
    for name in ('continuous_v1055_pause.request','fan_minrun_spotcheck_pause.request'):
        marker=ctx.R/'.codex-tmp'/name
        if marker.exists():marker.replace(ctx.DAY/(name+'.before_authorized_resume'))
    ctx.dump(ctx.DAY/'resume_authorization.json',dict(at=ctx.now(),instruction='接着测试！认真烧录测试！',
        versions=q['versions_after'],profile=q['profile_after'],restore_before_next=True))
    print('DEPLOYMENT VERIFIED; parameters preserved; authorized resume',flush=True)


if __name__=='__main__':
    try:main()
    except BaseException:
        ctx.dump(ctx.DAY/'deployment_error.json',dict(at=ctx.now(),error=traceback.format_exc()))
        raise
