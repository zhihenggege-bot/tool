"""Passive330 SWD observation only; no serial port, reset, halt, or memory writes."""
from pathlib import Path
import argparse,json,struct,time
from elftools.elf.elffile import ELFFile
from pyocd.core.helpers import ConnectHelper

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--samples',type=int,default=150)
    args=parser.parse_args();assert 1<=args.samples<=1500
    axf=next((ROOT/'.codex-tmp/shared_type_v1058_20261110/BENCH_ONLY_3S').glob('*10.58*.axf'))
    with axf.open('rb') as f:sy={s.name:(s['st_value'],s['st_size']) for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols() if s.name}
    path=ROOT/'测试证据/台架执行_20261111'/('passive330_scheduler_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=time.strftime('%Y-%m-%dT%H:%M:%S%z'),read_only=True,serial_opened=False,
        source_axf=str(axf.relative_to(ROOT)),samples=[])
    def save():
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8')
        temporary.replace(path)
    save()
    with ConnectHelper.session_with_chosen_probe(unique_id='50FF73067289515145451367',target_override='stm32f407ze',
        options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
        t=ss.target;began=time.monotonic()
        q['core_state_at_attach']=str(t.get_state());save()
        for _ in range(args.samples):
            row=dict(t=time.monotonic(),elapsed_s=time.monotonic()-began)
            for name in ('Systick_1ms','SendParaAddr3','PSC316PollRound','PSC316BusActive','PSC316BusUnit',
                         'PSC316BusFunction','PSC316BusAddress','PSC316BusCount','PSC316BusTick',
                         'PSC316BusDrainUntil','ModuleNum','SendParaAddr1','OLD_UnitWriteStatusUrgencyStop',
                         'PSC316UnitLastRespTick','outboardcount','PSC316WriteJob',
                         'PSC316WriteJobTick','PSC316EevManSent','PSC316EevManRelease',
                         'PSC316WriteState','PSC316WriteError','PSC316PageUnit',
                         'PSC316PageLoaded','PSC316PageShadow'):
                if name not in sy:continue
                a,n=sy[name];raw=bytes(t.read_memory_block8(a,n))
                row[name]=int.from_bytes(raw,'little') if n in (1,2,4,8) and name!='PSC316PollRound' else list(raw)
            p=sy['Parameter'][0]
            if 'PSC316WriteJob' in sy:
                a,n=sy['PSC316WriteJob'];raw=bytes(t.read_memory_block8(a,n))
                row['write_job_decoded']=dict(zip(('active','phase','unit','retry','count','address'),struct.unpack('<4B2H',raw[:8])))
                row['write_job_decoded']['values']=list(struct.unpack('<'+'h'*((n-8)//2),raw[8:]))
            row['eev_manual_sources']=list(struct.unpack('<16h',bytes(t.read_memory_block8(p+2*220,32))))
            row['legacy_page_881_884']=list(struct.unpack('<4h',bytes(t.read_memory_block8(p+2*881,8))))
            row['run_command']=t.read16(p+2*398)
            row['layers']=list(struct.unpack('<2H',bytes(t.read_memory_block8(p+2*2598,4))))
            row['faults1']=list(struct.unpack('<28H',bytes(t.read_memory_block8(p+2*2022,56))))
            row['fault_cache1']=list(struct.unpack('<28H',bytes(t.read_memory_block8(sy['PSC316FaultMirror'][0],56))))
            row['target_count']=t.read16(p+2*881)
            row['actual_count']=t.read16(p+2*119)
            q['samples'].append(row)
            if len(q['samples'])%15==0:save()
            time.sleep(.8)
        q['core_state_at_finish']=str(t.get_state())
    q['finished']=time.strftime('%Y-%m-%dT%H:%M:%S%z');save()
    print('PASSIVE EVIDENCE',path,flush=True)


if __name__=='__main__':main()
