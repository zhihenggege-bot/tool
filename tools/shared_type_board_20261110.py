"""Stopped, isolated-load bench verification of shared VFD and separate165/166 writes."""
import os
os.environ['PSC_BENCH_PACKAGE']='.codex-tmp/shared_type_v1058_20261110'
os.environ['PSC_BENCH_INDOOR_VERSION']='10.58'
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

ROOT=rt.R;PACKAGE=ROOT/'.codex-tmp/shared_type_v1058_20261110/BENCH_ONLY_3S'
DAY=ROOT/'测试证据/机型风机全局共享_20261110'
BOARDS=[tuple(list(b[:-1])+[b[-1].replace('12.39','12.40')]) for b in rt.BOARDS]
SOURCES=list(range(1331,1340))+list(range(1389,1400))
NEW=[1340,1341,1342]
EXPECTED=[330,10,58,2026,11,10,316,12,40,2026,11,10,316,12,40,2026,11,10]

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
    assert q['versions_before']==[330,10,57,2026,11,10,316,12,40,2026,11,10,316,12,40,2026,11,10]
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
        def actual_global():
            rows=[]
            for board in BOARDS[:2]:
                sy=symbols(board)
                with rt.ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
                    options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
                    t=ss.target;p=sy['Parameter'][0]
                    rows.append(dict(board=board[0],values={str(a):t.read16(p+2*a) for a in (39,56,60,107,165,166,200,1501)},
                                     output=list(t.read_memory_block8(*sy['output']))))
            return rows
        def settle_pair(pair):
            began=time.monotonic();stable=None
            while True:
                actual=actual_global()
                mirrors=[rd(1830,2),rd(1878,2)]
                ready=mirrors==[pair,pair] and all([r['values']['165'],r['values']['166']]==pair and not any(r['output']) for r in actual)
                if ready:
                    if stable is None:stable=time.monotonic()
                    if time.monotonic()-stable>=2:return actual
                else:stable=None
                assert time.monotonic()-began<80,('pair propagation',pair,mirrors,actual)
                time.sleep(.5)
        assert rd(1343,2)==q['outdoor_before'][0][:2],('new type sources not seeded',rd(1343,2))
        case('type sources adopt existing1# pair',source=rd(1343,2),actual=actual_global())
        for address,value in ((1343,1),(1344,2),(1344,4),(1343,2)):
            before=rd(1343,2);wr(address,value);after=rd(1343,2)
            assert after[1-(address-1343)]==before[1-(address-1343)]
            actual=settle_pair(after)
            legal=(after[1] in ({0:(0,1),1:(2,3),2:(2,4)}[after[0]]))
            assert all(bool(r['values']['1501']&64)==(not legal) for r in actual)
            case('shared independent'+str(address),before=before,source=after,actual=actual,legal=legal)
        for a,v in ((1343,-1),(1343,3),(1344,-1),(1344,5)):
            before=rd(1343,2);errors=[]
            try:wr(a,v)
            except Exception as ex:errors.append(repr(ex))
            assert rd(1343,2)==before
            case('type reject'+str((a,v)),source=before,protocol_errors=errors)
        for unit in (1,2):
            base=1830+48*(unit-1);errors=[]
            try:wr(base,0)
            except Exception as ex:errors.append(repr(ex))
            assert rd(base+44)==[9]
            case('shared on rejects independent165 unit'+str(unit),diagnostics=rd(base+42,6),protocol_errors=errors)
        wr(1319,0)
        monitor=object.__new__(Psc330MonitorApp);monitor.values={}
        monitor.read_now=lambda a,n:rd(a,n);monitor.write_single=lambda a,v:wr(a,v)
        # Shared off remains fully independent, and sources mirror unit1.
        monitor.write_outdoor_spec_field(1,165,1);monitor.write_outdoor_spec_field(1,166,3)
        monitor.write_outdoor_spec_field(2,165,0);monitor.write_outdoor_spec_field(2,166,1)
        began=time.monotonic()
        while rd(1343,2)!=[1,3]:
            assert time.monotonic()-began<40;time.sleep(.5)
        assert rd(1830,2)==[1,3] and rd(1878,2)==[0,1]
        case('shared off independent units',source=rd(1343,2),actual=actual_global())
        wr(1319,1);actual=settle_pair([1,3]);case('reenable shares unit1 pair',actual=actual)
        # Existing globals are always synchronized, including when1319=0.
        q['global_original']={str(a):rd(a)[0] for a in (39,56,60,107,365)};save()
        for enabled in (0,1):
            wr(1319,enabled)
            for a,target,values in ((39,39,(0,1,2,3)),(107,107,(2,1)),(365,200,(0,1)),(56,56,(3500,3800)),(60,60,(6,5))):
                for value in values:
                    wr(a,value);began=time.monotonic();stable=None
                    while True:
                        actual=actual_global()
                        if all(r['values'][str(target)]==value and not any(r['output']) for r in actual):
                            if stable is None:stable=time.monotonic()
                            if time.monotonic()-stable>=2:break
                        else:stable=None
                        assert time.monotonic()-began<80,('global propagation',enabled,a,value,actual)
                        time.sleep(.4)
                    assert rd(a)==[value],('330 source readback',a,value,rd(a))
                    case('global source'+str(a)+'='+str(value)+' shared'+str(enabled),source=rd(a),target316=target,actual=actual)
        for a,v in q['global_original'].items():wr(int(a),v)
        q['test_passed']=True
    except BaseException:
        q['error']=traceback.format_exc();save();raise
    finally:
        try:
            if not c.is_open:c=rt.client()
            wr(398,0)
            monitor=object.__new__(Psc330MonitorApp);monitor.values={}
            monitor.read_now=lambda a,n:rd(a,n);monitor.write_single=lambda a,v:wr(a,v)
            wr(1319,0)
            for a,v in q.get('global_original',{}).items():wr(int(a),v)
            for unit,values in enumerate(q['outdoor_before'],1):
                for p in (165,166):monitor.write_outdoor_spec_field(unit,p,values[p-165])
            wr(1319,1)
            c.write_multiple_registers(1,1343,q['outdoor_before'][0][:2])
            for a,v in q['shared_before'].items():wr(int(a),rt.signed16(v))
            c.write_multiple_registers(1,1340,q['outdoor_before'][0][11:14])
            settle(q['outdoor_before'][0][11:14])
            settle_pair(q['outdoor_before'][0][:2])
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
