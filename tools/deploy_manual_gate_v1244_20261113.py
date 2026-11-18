"""Authorized two316 upgrade, full backup/readback; unchanged330 verified only."""
import hashlib
import json
import time
import traceback
import manual_fix_context_20261113 as ctx
from pyocd.flash.file_programmer import FileProgrammer
from verify_board_flash_vs_hex import parse_hex,blocks_of

g=ctx.g
OLD=ctx.R/'.codex-tmp/ambient_scope_v1061_20261112/BENCH_ONLY_3S'

def verify(t,path):
    mem=parse_hex(path)
    for lo,hi in blocks_of(mem):
        for a in range(lo,hi,4096):
            n=min(4096,hi-a)
            assert bytes(t.read_memory_block8(a,n))==bytes(mem[a+i] for i in range(n)),(path.name,hex(a))
    return len(mem)

def main():
    path=ctx.DAY/'deployment.json';assert not path.exists()
    m=json.loads((ctx.I/'manifest.json').read_text('utf8'))
    assert all(g.runtime.sha(ctx.R/n)==h for n,h in m['source_inventory'].items())
    assert all(g.runtime.sha(ctx.I/n)==h for n,h in m['artifacts'].items())
    regression=json.loads((ctx.I.parent/'ARM_regression.json').read_text('utf8'))
    assert all(r['passed'] for r in regression['results'])
    q=dict(started=g.now(),authorization='修改代码并复测',profile='BENCH_ONLY_3S',boards=[],
           source_inventory=m['source_inventory'],artifacts=m['artifacts'],unchanged_indoor=True)
    c=g.runtime.client()
    try:
        q['versions_before']=c.read_holding_registers(1,2622,18)
        assert q['versions_before']==[330,10,61,2026,11,12,316,12,43,2026,11,12,316,12,43,2026,11,12]
        q['snapshot_before']=g.runtime.snap(c)
        assert g.loads_off(q['snapshot_before']) and q['snapshot_before']['state'][9]==0
        assert c.read_holding_registers(1,398,1)==[0]
        q['config_before']={}
        for a,n in [(0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2),(1319,26),(1389,11),(1830,96),(2680,98)]:
            q['config_before'].update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        g.dump(path,q)
    finally:c.close()
    for board in g.BOARDS:
        label,uid,target,device,flash_size,ram_size,stem=board
        row=dict(board=label,probe=uid,programmed=False);q['boards'].append(row)
        with g.ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
             options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target;assert t.read32(0xE0042000)&0xfff==device
            row['old_verified_bytes']=verify(t,OLD/(stem.replace('12.44','12.43')+'.hex'))
            if label!='330':
                t.halt();old_debug=t.read32(0xE0042008);programmed=False
                try:
                    for suffix,address,size in [('flash',0x08000000,flash_size),('sram',0x20000000,ram_size)]:
                        dest=ctx.DAY/f'{label}_before_{suffix}.bin';assert not dest.exists()
                        dest.write_bytes(bytes(t.read_memory_block8(address,size)))
                        row[suffix+'_backup']=dict(path=dest.name,size=size,sha256=g.runtime.sha(dest))
                    g.dump(path,q)
                    t.write32(0xE0042008,old_debug|0x1800);t.reset_and_halt()
                    t.write32(0xE0042008,t.read32(0xE0042008)|0x1800)
                    row['programming_started']=g.now();g.dump(path,q)
                    FileProgrammer(ss,chip_erase='sector',trust_crc=False).program(str(ctx.I/(stem+'.hex')))
                    row['programmed']=programmed=True
                    row['new_verified_bytes']=verify(t,ctx.I/(stem+'.hex'))
                    row['flash_verified']=True;g.dump(path,q)
                finally:
                    t.write32(0xE0042008,old_debug)
                    if programmed:t.reset()
                    else:t.resume()
            else:
                row['new_verified_bytes']=verify(t,ctx.I/(stem+'.hex'));row['flash_verified']=True
            row['finished']=g.now();g.dump(path,q)
        print('FLASH VERIFIED',label,'programmed',row['programmed'],flush=True)
    c=g.runtime.client()
    try:
        end=time.monotonic()+100
        while True:
            versions=c.read_holding_registers(1,2622,18)
            if versions==g.runtime.EXPECTED:break
            assert time.monotonic()<end,versions
            time.sleep(.5)
        q['versions_after']=versions
        time.sleep(5)
        q['config_after']={a:c.read_holding_registers(1,int(a),1)[0] for a in q['config_before']}
        q['configuration_changes']={a:[v,q['config_after'][a]] for a,v in q['config_before'].items()
                                    if int(a) not in (167,373) and not (1830<=int(a)<1926 and (int(a)-1830)%48 in range(42,47)) and q['config_after'][a]!=v}
        assert not q['configuration_changes'],q['configuration_changes']
        q['snapshot_after']=g.runtime.snap(c)
        assert g.loads_off(q['snapshot_after']) and q['snapshot_after']['state'][9]==0
        q.update(verified=True,finished=g.now());g.dump(path,q)
    finally:c.close()
    g.audit_module.audit('post_flash',True)

def finish_verified_programming():
    path=ctx.DAY/'deployment.json';q=json.loads(path.read_text('utf8'))
    assert len(q['boards'])==3 and all(b['flash_verified'] for b in q['boards'])
    q['finalization_note']='Initial comparison included read-only gateway +45 response counters (1875/1923); preserved deployment_error journal. Compare actual settings, record diagnostics separately.'
    c=g.runtime.client()
    try:
        q['versions_after']=c.read_holding_registers(1,2622,18)
        assert q['versions_after']==g.runtime.EXPECTED
        q['config_after']={a:c.read_holding_registers(1,int(a),1)[0] for a in q['config_before']}
        diff={a:[v,q['config_after'][a]] for a,v in q['config_before'].items() if q['config_after'][a]!=v}
        q['read_only_diagnostic_changes']={a:v for a,v in diff.items() if 1830<=int(a)<1926 and (int(a)-1830)%48 in range(42,47)}
        q['configuration_changes']={a:v for a,v in diff.items() if a not in q['read_only_diagnostic_changes'] and int(a) not in (167,373)}
        assert not q['configuration_changes'],q['configuration_changes']
        q['snapshot_after']=g.runtime.snap(c)
        assert g.loads_off(q['snapshot_after']) and q['snapshot_after']['state'][9]==0
        q.update(verified=True,finished=g.now());g.dump(path,q)
    finally:c.close()
    g.audit_module.audit('post_flash',True)

if __name__=='__main__':
    import sys
    try:
        if '--finish-verified-programming' in sys.argv:finish_verified_programming()
        else:main()
    except BaseException:
        g.dump(ctx.DAY/('deployment_error_'+time.strftime('%H%M%S')+'.json'),dict(at=g.now(),error=traceback.format_exc()))
        raise
