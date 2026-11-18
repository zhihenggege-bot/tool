"""Current-image readback and normal fault-reset inputs; never flash or halt."""
from v1055_bench_context_20261109 import *
from elftools.elf.elffile import ELFFile

DAY=R/'测试证据/内外机联合实测_20261110'

def symbols(board):
    with (I/(board[-1]+'.axf')).open('rb') as f:
        return {s.name:(s['st_value'],s['st_size']) for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols() if s.name}

def main():
    from verify_board_flash_vs_hex import parse_hex,blocks_of
    p=DAY/('image_and_reset_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),firmware_changed=False,halt_or_reset=False,boards=[],samples=[])
    c=runtime.client();sessions=[]
    try:
        assert loads_off(runtime.snap(c))
        for b in BOARDS:
            sy=symbols(b)
            ss=ConnectHelper.session_with_chosen_probe(unique_id=b[1],target_override=b[2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            ss.open();sessions.append((b,ss,sy))
            mem=parse_hex(I/(b[-1]+'.hex'));n=0
            for first,last in blocks_of(mem):
                for addr in range(first,last,4096):
                    count=min(4096,last-addr)
                    assert bytes(ss.target.read_memory_block8(addr,count))==bytes(mem[addr+i] for i in range(count)),(b[0],hex(addr))
                    n+=count
            q['boards'].append(dict(board=b[0],exact_flash_matches_selected_hex=True,verified_bytes=n,axf_sha256=hashlib.sha256((I/(b[-1]+'.axf')).read_bytes()).hexdigest()))
            dump(p,q);print('IMAGE MATCH',b[0],n,flush=True)
        def sample(label):
            s=dict(at=now(),label=label,snapshot=runtime.snap(c),outdoor=[])
            for b,ss,sy in sessions[:2]:
                t=ss.target;base=sy['Parameter'][0]
                words=lambda a,n:[t.read16(base+2*(a+i)) for i in range(n)]
                s['outdoor'].append(dict(board=b[0],alarms=words(600,28),commands=words(1400,12),raw_hp=[t.read8(sy[x][0]) for x in ('X_00','X_02')],pressures=words(1443,4)))
            q['samples'].append(s);dump(p,q);return s
        sample('before normal indoor reset')
        c.write_single_register(1,524,1);time.sleep(.3);c.write_single_register(1,524,0)
        end=time.monotonic()+16
        while True:
            s=sample('normal indoor reset propagation')
            print('RESET',[(x['board'],x['alarms'][6:8],x['commands'][2]) for x in s['outdoor']],flush=True)
            if all(not any(x['alarms']) for x in s['outdoor']):break
            if time.monotonic()>=end:break
            time.sleep(1)
        if any(any(x['alarms']) for x in s['outdoor']):
            q['direct_normal_outdoor_reset_input']=True
            for b,ss,sy in sessions[:2]:ss.target.write16(sy['Parameter'][0]+1402*2,1);ss.target.flush()
            time.sleep(1);s=sample('after outdoor normal reset input1402')
        assert all(not any(x['alarms']) for x in s['outdoor']),s
        assert loads_off(s['snapshot'])
        q.update(healthy_stopped_precondition=True,finished=now());dump(p,q)
        print('HEALTHY STOPPED',p,flush=True)
    except BaseException:q['error']=traceback.format_exc();dump(p,q);raise
    finally:
        for b,ss,sy in sessions:ss.close()
        c.close()

if __name__=='__main__':main()
