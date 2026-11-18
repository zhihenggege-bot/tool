"""Upgrade only330 after targeted cases finish and all outputs are off."""
import manual_reset_fix_context_20261113 as ctx
from deploy_manual_gate_v1244_20261113 import verify
from pyocd.flash.file_programmer import FileProgrammer
import json
import time
import traceback

g=ctx.g
OLD=ctx.R/'.codex-tmp/manual_gate_v1244_20261113/BENCH_ONLY_3S'
EXPECTED_BEFORE=[330,10,61,2026,11,12,316,12,44,2026,11,13,316,12,44,2026,11,13]
ARM_FILE='reset_ARM_regression.json'

def finalize(path,q):
    c=g.runtime.client()
    try:
        end=time.monotonic()+90
        while True:
            try:q['versions_after']=c.read_holding_registers(1,2622,18)
            except Exception as exc:
                q.setdefault('boot_read_retries',[]).append(dict(at=g.now(),error=repr(exc)))
                q['versions_after']=[]
            if q['versions_after']==g.runtime.EXPECTED:break
            assert time.monotonic()<end,q['versions_after'];time.sleep(.5)
        time.sleep(22)
        q['config_after']={a:c.read_holding_registers(1,int(a),1)[0] for a in q['config_before']}
        q['configuration_changes']={a:[v,q['config_after'][a]] for a,v in q['config_before'].items()
            if int(a) not in (167,373) and not (1830<=int(a)<1926 and (int(a)-1830)%48 in range(42,47)) and q['config_after'][a]!=v}
        assert not q['configuration_changes'],q['configuration_changes']
        q['snapshot_after']=g.runtime.snap(c)
        assert g.loads_off(q['snapshot_after']) and q['snapshot_after']['state'][9]==0
        q.update(verified=True,finished=g.now());g.dump(path,q)
    finally:c.close()
    g.audit_module.audit('post_flash',True)

def main():
    path=ctx.DAY/'deployment.json';assert not path.exists()
    m=json.loads((ctx.I/'manifest.json').read_text('utf8'))
    assert all(g.runtime.sha(ctx.R/n)==v for n,v in m['source_inventory'].items())
    assert all(g.runtime.sha(ctx.I/n)==v for n,v in m['artifacts'].items())
    assert all(r['passed'] for r in json.loads((ctx.I.parent/ARM_FILE).read_text('utf8')))
    q=dict(started=g.now(),authorization='修改代码并复测',boards=[],source_inventory=m['source_inventory'],artifacts=m['artifacts'])
    c=g.runtime.client()
    try:
        q['versions_before']=c.read_holding_registers(1,2622,18)
        assert q['versions_before']==EXPECTED_BEFORE
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
        row=dict(board=label,programmed=False);q['boards'].append(row)
        with g.ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
             options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target;assert t.read32(0xE0042000)&0xfff==device
            before_stem=stem if label!='330' else f'PSC330_V10.{EXPECTED_BEFORE[2]}_BENCH_ONLY_3S'
            row['old_verified_bytes']=verify(t,OLD/(before_stem+'.hex'))
            if label=='330':
                t.halt();old_debug=t.read32(0xE0042008);programmed=False
                try:
                    for suffix,a,n in [('flash',0x08000000,flash_size),('sram',0x20000000,ram_size)]:
                        p=ctx.DAY/f'330_before_{suffix}.bin';assert not p.exists()
                        p.write_bytes(bytes(t.read_memory_block8(a,n)))
                        row[suffix+'_backup']=dict(path=p.name,sha256=g.runtime.sha(p),size=n)
                    g.dump(path,q)
                    t.write32(0xE0042008,old_debug|0x1800);t.reset_and_halt()
                    t.write32(0xE0042008,t.read32(0xE0042008)|0x1800)
                    FileProgrammer(ss,chip_erase='sector',trust_crc=False).program(str(ctx.I/(stem+'.hex')))
                    row['programmed']=programmed=True
                    row['verified_bytes']=verify(t,ctx.I/(stem+'.hex'));row['flash_verified']=True
                    g.dump(path,q)
                finally:
                    t.write32(0xE0042008,old_debug)
                    if programmed:t.reset()
                    else:t.resume()
            else:
                row['verified_bytes']=verify(t,ctx.I/(stem+'.hex'));row['flash_verified']=True
            row['finished']=g.now();g.dump(path,q)
        print('FLASH VERIFIED',label,row['programmed'],flush=True)
    finalize(path,q)

if __name__=='__main__':
    import sys
    try:
        if '--finish-verified-programming' in sys.argv:
            p=ctx.DAY/'deployment.json';q=json.loads(p.read_text('utf8'))
            assert len(q['boards'])==3 and all(r['flash_verified'] for r in q['boards'])
            q['finalization_note']='Full flash readbacks completed; retained first startup no-response journal; finalizing without reprogramming.'
            finalize(p,q)
        else:main()
    except BaseException:
        g.dump(ctx.DAY/('deployment_error_'+time.strftime('%H%M%S')+'.json'),dict(at=g.now(),error=traceback.format_exc()));raise
