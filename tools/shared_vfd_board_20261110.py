"""Stopped, isolated-load bench verification of shared VFD and separate165/166 writes."""
import os
os.environ['PSC_BENCH_PACKAGE']='.codex-tmp/shared_vfd_v1057_20261110'
os.environ['PSC_BENCH_INDOOR_VERSION']='10.57'
import base64
import hashlib
import json
import time
import traceback
from contextlib import ExitStack
import run_indoor_bench_20261105 as rt
from test_defrost_lifecycle_arm import Firmware
from elftools.elf.elffile import ELFFile
from app import Psc330MonitorApp

ROOT=rt.R;PACKAGE=ROOT/'.codex-tmp/shared_vfd_v1057_20261110/BENCH_ONLY_3S'
DAY=ROOT/'测试证据/变频风机三项共享_20261110'
BOARDS=[tuple(list(b[:-1])+[b[-1].replace('12.39','12.40')]) for b in rt.BOARDS]
SOURCES=list(range(1331,1340))+list(range(1389,1400))
NEW=[1340,1341,1342]
EXPECTED=[330,10,57,2026,11,10,316,12,40,2026,11,10,316,12,40,2026,11,10]

def symbols(board):
    with (PACKAGE/(board[-1]+'.axf')).open('rb') as file:
        return {s.name:(s['st_value'],s['st_size']) for s in ELFFile(file).get_section_by_name('.symtab').iter_symbols() if s.name}

def main():
    DAY.mkdir(exist_ok=True)
    path=DAY/('board_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=rt.now(),scope='Stopped boards; normal330 Modbus settings; software readback, no physical terminals',
           cases=[],flashed=False,restored=False)
    def save():rt.dump(path,q)
    m=json.loads((PACKAGE/'manifest.json').read_text('utf8'))
    assert all(rt.sha(ROOT/p)==h for p,h in m['source_inventory'].items())
    assert all(rt.sha(PACKAGE/p)==h for p,h in m['artifacts'].items())
    q['source_inventory']=m['source_inventory'];q['artifact_sha256']=m['artifacts']
    c=rt.client()
    def rd(a,n=1):return c.read_holding_registers(1,a,n)
    def wr(a,v):c.write_single_register(1,a,v&65535)
    def case(name,**data):
        q['cases'].append(dict(name=name,at=rt.now(),**data));save();print('BOARD',name,flush=True)
    def stopped():
        s=rt.snap(c)
        assert s['state'][9]==0 and rt.loads_off(s),s
        assert rd(398)==[0]
        return s
    def board_readbacks():
        rows=[]
        for b in BOARDS:
            sy=symbols(b)
            with rt.ConnectHelper.session_with_chosen_probe(unique_id=b[1],target_override=b[2],
                     options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
                t=ss.target;p=sy['Parameter'][0]
                row=dict(board=b[0],output=list(t.read_memory_block8(*sy['output'])))
                assert not any(row['output']),row
                if b[0]!='330':
                    row['settings165_181']=[t.read16(p+2*a) for a in range(165,182)]
                    row['fault_layer']=t.read16(p+3002)
                rows.append(row)
        return rows
    def settle(values,seconds=3):
        began=time.monotonic();since=None;last=None
        while True:
            last=[rd(1841,3),rd(1889,3)]
            if last==[values,values]:
                if since is None:since=time.monotonic()
                if time.monotonic()-since>=seconds:return last
            else:since=None
            assert time.monotonic()-began<65,('shared propagation timeout',values,last)
            time.sleep(.35)
    q['versions_before']=rd(2622,18)
    assert q['versions_before']==[330,10,56,2026,11,10,316,12,40,2026,11,10,316,12,40,2026,11,10]
    q['snapshot_before']=stopped()
    q['switch_before']=rd(1319)[0]
    q['shared_before']={str(a):rd(a)[0] for a in SOURCES}
    q['outdoor_before']=[rd(1830,42),rd(1878,42)]
    assert q['outdoor_before'][0][11:14]==q['outdoor_before'][1][11:14], 'Cannot restore different unit values under shared mode'
    q['config_before']={}
    for a,n in ((0,125),(125,125),(250,125),(375,125),(1229,60)):
        q['config_before'].update({str(a+i):v for i,v in enumerate(rd(a,n))})
    save();c.close()
    # Same stopped bench programming method used for the earlier authorized upgrade.
    b=BOARDS[2];sy=symbols(b)
    try:
        with rt.ConnectHelper.session_with_chosen_probe(unique_id=b[1],target_override=b[2],
                 options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target;assert t.read32(0xE0042000)&0xfff==0x413
            t.halt();reg=0xE0042008;old=t.read32(reg);programmed=False
            try:
                for name,addr,n in (('flash',0x08000000,512*1024),('sram',0x20000000,128*1024)):
                    raw=bytes(t.read_memory_block8(addr,n));backup=DAY/(path.stem+'_'+name+'.bin.base64')
                    backup.write_text(base64.b64encode(raw).decode('ascii'),'ascii')
                    assert base64.b64decode(backup.read_bytes())==raw
                    q[name+'_backup']=dict(path=backup.name,bytes=n,sha256=hashlib.sha256(raw).hexdigest())
                save();t.write32(reg,old|0x1800);t.reset_and_halt();t.write32(reg,t.read32(reg)|0x1800)
                rt.FileProgrammer(ss,chip_erase='sector',trust_crc=False).program(str(PACKAGE/(b[-1]+'.hex')))
                programmed=True;q['flashed']=True;save()
                memory=rt.parse_hex(PACKAGE/(b[-1]+'.hex'));verified=0
                for lo,hi in rt.blocks_of(memory):
                    for addr in range(lo,hi,4096):
                        n=min(4096,hi-addr)
                        assert bytes(t.read_memory_block8(addr,n))==bytes(memory[addr+i] for i in range(n))
                        verified+=n
                q['verified_flash_bytes']=verified;save()
            finally:
                t.write32(reg,old)
                if programmed:t.reset()
                else:t.resume()
        c=rt.client()
        deadline=time.monotonic()+90
        while True:
            try:v=rd(2622,18)
            except Exception:v=[]
            if v==EXPECTED:break
            assert time.monotonic()<deadline,v;time.sleep(.5)
        time.sleep(22)
        q['versions_after']=v;q['profile_after']=rd(1298,2)
        assert q['profile_after']==[3,15107]
        stopped()
        for a,v in q['shared_before'].items():wr(int(a),rt.signed16(v))
        wr(1319,1)
        original=q['outdoor_before'][0][11:14]
        q['new_sources_seeded']=rd(1340,3)
        assert q['new_sources_seeded']==original,(q['new_sources_seeded'],original)
        settle(original)
        # The actual monitor method issues a single normal330 FC06 write.
        monitor=object.__new__(Psc330MonitorApp);monitor.values={}
        monitor.read_now=lambda a,n:rd(a,n)
        monitor.write_single=lambda a,v:wr(a,v)
        for unit in (1,2):
            base=1830+48*(unit-1)
            for order in ((165,166),(166,165)):
                targets={165:1,166:2} if order==(165,166) else {165:2,166:4}
                for p in order:
                    before=rd(base,2)
                    pair=monitor.write_outdoor_spec_field(unit,p,targets[p])
                    assert pair[1-(p-165)]==before[1-(p-165)],(unit,p,before,pair)
                    actual=board_readbacks()[unit-1]['settings165_181'][:2]
                    assert actual==list(pair)
                    case(f'unit{unit}/independent{p}/order{order}',before=before,after=pair,actual=actual)
        for values in ([30,0,1],[45,5,10],[50,30,20]):
            c.write_multiple_registers(1,1340,values)
            assert rd(1340,3)==values
            feedback=settle(values)
            actual=board_readbacks()
            assert all(r['settings165_181'][11:14]==values for r in actual[:2])
            case('shared-'+str(values),source=rd(1340,3),mirrors=feedback,actual=actual)
        for a,v in ((1340,29),(1340,51),(1341,-1),(1341,31),(1342,0),(1342,21)):
            before=rd(1340,3);errors=[]
            try:wr(a,v)
            except Exception as ex:errors.append(repr(ex))
            assert rd(1340,3)==before
            case(f'reject-{a}-{v}',before=before,after=rd(1340,3),protocol_errors=errors)
        for unit in (1,2):
            base=1830+48*(unit-1);errors=[]
            try:wr(base+11,40)
            except Exception as ex:errors.append(repr(ex))
            assert rd(base+44)==[9]
            case(f'shared-on-reject-unit{unit}-direct',diagnostics=rd(base+42,6),protocol_errors=errors)
        wr(1319,0)
        before=rd(1340,3)
        try:wr(1340,35)
        except Exception:pass
        assert rd(1340,3)==before
        monitor.write_outdoor_gateway_register(1830,1841,176,40)
        monitor.write_outdoor_gateway_register(1878,1889,176,45)
        time.sleep(4)
        assert rd(1841)==[40] and rd(1889)==[45]
        assert rd(1340)==[40]
        case('shared-off-independent',unit1=rd(1841,3),unit2=rd(1889,3),source_mirror=rd(1340,3))
        q['test_passed']=True
    except BaseException:
        q['error']=traceback.format_exc();save();raise
    finally:
        try:
            if not c.is_open:c=rt.client()
            wr(398,0)
            monitor=object.__new__(Psc330MonitorApp);monitor.values={}
            monitor.read_now=lambda a,n:rd(a,n);monitor.write_single=lambda a,v:wr(a,v)
            for unit,values in enumerate(q['outdoor_before'],1):
                for p in (165,166):monitor.write_outdoor_spec_field(unit,p,values[p-165])
            wr(1319,1)
            for a,v in q['shared_before'].items():wr(int(a),rt.signed16(v))
            c.write_multiple_registers(1,1340,q['outdoor_before'][0][11:14])
            settle(q['outdoor_before'][0][11:14])
            wr(1319,q['switch_before'])
            q['outdoor_after']=[rd(1830,42),rd(1878,42)]
            assert q['outdoor_after']==q['outdoor_before']
            q['config_after']={a:rd(int(a))[0] for a in q['config_before']}
            q['config_changes']={a:[v,q['config_after'][a]] for a,v in q['config_before'].items()
                                 if v!=q['config_after'][a] and int(a) not in (167,373)}
            assert not q['config_changes'],q['config_changes']
            q['final_boards']=board_readbacks();q['final_snapshot']=stopped()
            assert not any(q['final_snapshot']['faults'])
            q['source_mismatches']=[p for p,h in m['source_inventory'].items() if rt.sha(ROOT/p)!=h]
            assert not q['source_mismatches']
            q['restored']=True
        except BaseException:q['cleanup_error']=traceback.format_exc();save();raise
        finally:
            c.close();q['finished']=rt.now();save();print('EVIDENCE',path,flush=True)

if __name__=='__main__':main()
