"""Independent read-only resolution of asynchronous destination restore."""
from v1055_bench_context_20261109 import *
from elftools.elf.elffile import ELFFile


def main():
    source=D/'remaining571_heat_dynamic_defrost_nonvent_paired_eev_mode_1_20261106_161912.json'
    old=json.loads(source.read_text('utf8'))
    with (I/(BOARDS[0][-1]+'.axf')).open('rb') as f:
        sy={s.name:(s['st_value'],s['st_size']) for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols() if s.name}
    r=dict(at=now(),source=source.relative_to(R).as_posix(),read_only=True,original_failure_preserved=True,checks=[],restored=False)
    c=runtime.client()
    try:
        with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            for addr in (1865,1866,1867,1868):
                writes=[x for x in old['gateway_writes'] if x['address']==addr]
                # No write event means gateway() confirmed this unchanged
                # preexisting setting and returned without mutation.
                expected=writes[0]['before'] if writes else {1865:1,1866:200}[addr]
                got=c.read_holding_registers(1,addr,1)[0];dest=ss.target.read16(sy['Parameter'][0]+(165+(addr-1830)%48)*2)
                r['checks'].append(dict(address=addr,expected=expected,mirror=got,destination=dest,passed=got==dest==expected))
        assert all(x['passed'] for x in r['checks']),r
        assert old['restored'] is True and not old.get('restore_mismatches'),old.get('restore_mismatches')
        r['restored']=True
    finally:
        c.close();dump(D/('remaining571_heat_dynamic_paired_cleanup_confirmation_'+time.strftime('%H%M%S')+'.json'),r)
    print(json.dumps(r,ensure_ascii=False))


if __name__=='__main__':main()
