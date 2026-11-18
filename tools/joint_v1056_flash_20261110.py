"""Stopped isolated-load bench upgrade; backup, program and exact readback.

Only sector program flash covered by the selected HEX; do not erase EEPROM.
"""
from joint_v1056_context_20261110 import *
import base64
from verify_board_flash_vs_hex import parse_hex, blocks_of
from pyocd.flash.file_programmer import FileProgrammer


def main():
    path=DAY/'flash_v1056_v1240.json'
    assert not path.exists(), 'Preserve flash journal; inspect before retry'
    m=json.loads((I/'manifest.json').read_text('utf8'))
    assert m['bench_only'] and not m['flashed']
    for p,h in m['source_inventory'].items():assert hashlib.sha256((R/p).read_bytes()).hexdigest()==h,p
    for p,h in m['artifacts'].items():assert hashlib.sha256((I/p).read_bytes()).hexdigest()==h,p
    q=dict(started=now(),user_authorization='继续测试修复版及未测内外机项目',
           profile='BENCH_ONLY_3S',isolated_load_bench=True,physical_terminal_measurement=False,
           source_inventory=m['source_inventory'],artifact_sha256=m['artifacts'],boards=[])
    c=runtime.client()
    try:
        q['versions_before']=c.read_holding_registers(1,2622,18)
        assert q['versions_before']==[330,10,55,2026,11,9,316,12,39,2026,11,5,316,12,39,2026,11,5]
        q['snapshot_before']=runtime.snap(c)
        assert q['snapshot_before']['state'][9]==0 and loads_off(q['snapshot_before'])
        assert c.read_holding_registers(1,398,1)==[0]
        q['config_before']={}
        for a,n in ((0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2),(1331,85)):
            q['config_before'].update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        probes={x.unique_id for x in ConnectHelper.get_all_connected_probes(blocking=False)}
        assert {b[1] for b in BOARDS}.issubset(probes)
        dump(path,q)
    finally:c.close()
    for label,uid,target,device,flash_size,ram_size,stem in BOARDS:
        entry=dict(board=label,uid=uid,started=now(),programmed=False)
        q['boards'].append(entry);dump(path,q)
        with ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target;assert t.read32(0xE0042000)&0xfff==device
            reg,bits=(0xE0042004,0x300) if device==0x414 else (0xE0042008,0x1800)
            t.halt();old_debug=t.read32(reg);programmed=False
            try:
                for suffix,addr,size in (('flash',0x08000000,flash_size),('sram',0x20000000,ram_size)):
                    raw=bytes(t.read_memory_block8(addr,size))
                    backup=DAY/f'{label}_before_fix_{suffix}.bin.base64'
                    assert not backup.exists()
                    backup.write_text(base64.b64encode(raw).decode('ascii'),encoding='ascii')
                    assert base64.b64decode(backup.read_bytes())==raw
                    entry[suffix+'_backup']=dict(path=backup.name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
                dump(path,q)
                t.write32(reg,old_debug|bits);t.reset_and_halt();t.write32(reg,t.read32(reg)|bits)
                FileProgrammer(ss,chip_erase='sector',trust_crc=False).program(str(I/(stem+'.hex')))
                programmed=True;entry['programmed']=True
                mem=parse_hex(I/(stem+'.hex'));verified=0
                for lo,hi in blocks_of(mem):
                    for a in range(lo,hi,4096):
                        n=min(4096,hi-a)
                        assert bytes(t.read_memory_block8(a,n))==bytes(mem[a+i] for i in range(n)),(label,hex(a))
                        verified+=n
                entry.update(verified_bytes=verified,flash_verified=True,finished=now());dump(path,q)
            except BaseException:
                entry['error']=traceback.format_exc();dump(path,q);raise
            finally:
                t.write32(reg,old_debug)
                if programmed:t.reset()
                else:t.resume()
        print('FLASH VERIFIED',label,entry.get('verified_bytes'),flush=True)
    c=runtime.client()
    try:
        end=time.monotonic()+65
        while True:
            try:v=c.read_holding_registers(1,2622,18)
            except Exception:v=[]
            if v==runtime.EXPECTED:break
            assert time.monotonic()<end,v;time.sleep(.5)
        q['versions_after']=v
        sy=runtime.axf_symbols()
        with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            while True:
                t=ss.target
                if t.read8(sy['IndoorAiCfgLoaded'][0])==1 and t.read8(sy['eepromtt'][0])==3 and t.read32(sy['Systick_1ms'][0])>=21000:break
                assert time.monotonic()<end;time.sleep(.3)
        q['config_after']={}
        for a,n in ((0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2),(1331,85)):
            q['config_after'].update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        # 167/373 are existing runtime counters, not configuration changes.
        q['config_changes']={a:[v,q['config_after'][a]] for a,v in q['config_before'].items() if v!=q['config_after'][a] and int(a) not in (167,373)}
        q['snapshot_after']=runtime.snap(c);q['profile_after']=c.read_holding_registers(1,1298,2)
        assert not q['config_changes'],q['config_changes']
        assert q['snapshot_after']['state'][9]==0 and loads_off(q['snapshot_after'])
        assert q['profile_after']==[3,15107]
        q.update(passed=True,finished=now());dump(path,q)
    finally:c.close()
    print('UPGRADE COMPLETE',q['versions_after'],'configuration preserved',flush=True)


if __name__=='__main__':main()
