"""Preserve stopped emergency-defrost state, recover by normal commands only."""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench


def main():
    b=CheckedBench('emergency_defrost_recovery_diagnostic');sessions=[]
    try:
        from elftools.elf.elffile import ELFFile
        for board in BOARDS[:2]:
            with (I/(board[-1]+'.axf')).open('rb') as f:
                sy={s.name:(s['st_value'],s['st_size']) for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols() if s.name}
            ss=ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            ss.open();sessions.append((ss,sy))
        def sample(label):
            s=b.snapshot(label);s['phase_mirror']=b.rd(1550,2);s['outdoor_direct']=[]
            for ss,sy in sessions:
                t=ss.target;p=sy['Parameter'][0]
                row=dict(phase=[t.read16(p+1420*2+i*2) for i in range(2)],
                    comp=list(t.read_memory_block8(sy['Comp'][0],2)),
                    parameters={str(a):t.read16(p+a*2) for a in (1,2,191,192,193,194,195,196,197)})
                for name in ('PSC316DefrostState','PSC316DefrostStateTime','ModUrgencyStop','SysErrStatus','SysStep'):
                    if name in sy:
                        addr,size=sy[name];row[name]=int.from_bytes(bytes(t.read_memory_block8(addr,size)),'little')
                s['outdoor_direct'].append(row)
            b.log.setdefault('diagnostics',[]).append(s);b.save();print(label,s['phase_mirror'],s['outdoor_direct'],flush=True);return s
        before=sample('stopped emergency state before recovery')
        assert before['state'][9]==0 and loads_off(before)
        b.wr(398,0);b.reset_faults();b.config({236:0});began=time.monotonic()
        while True:
            s=sample('normal cooling selection while stopped, no lifecycle write')
            assert s['state'][9]==0 and loads_off(s),s
            if s['phase_mirror']==[0,0] and all(x['phase']==[0,0] for x in s['outdoor_direct']):break
            assert time.monotonic()-began<40,('normal command recovery did not clear lifecycle',s)
            time.sleep(2)
        b.log['recovery_confirmed']=True
        print('NORMAL COMMAND RECOVERY CONFIRMED',b.path,flush=True)
    except BaseException:b.log['error']=traceback.format_exc();b.save();raise
    finally:
        for ss,sy in sessions:ss.close()
        b.finish()


if __name__=='__main__':main()
