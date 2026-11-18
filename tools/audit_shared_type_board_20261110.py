"""Independent read-only hardware/settings/image audit after shared-parameter tests."""
import json
import subprocess
import time
import shared_type_board_20261110 as test
from verify_board_flash_vs_hex import parse_hex, blocks_of

def main():
    rt=test.rt
    prior_path=max(test.DAY.glob('board_*.json'),key=lambda p:p.stat().st_mtime)
    prior=json.loads(prior_path.read_text('utf8'))
    q=dict(started=rt.now(),read_only=True,source=prior_path.name,boards=[])
    c=rt.client()
    try:
        rd=lambda a,n=1:c.read_holding_registers(1,a,n)
        q['versions']=rd(2622,18);q['profile']=rd(1298,2)
        q['outdoor']=[rd(1830,42),rd(1878,42)]
        q['shared']={a:rd(int(a))[0] for a in prior['shared_before']}
        q['new_shared']=rd(1340,3);q['shared_type']=rd(1343,2);q['switch']=rd(1319)[0]
        q['globals']={a:rd(int(a))[0] for a in prior['global_original']}
        q['commands']=[rd(398)[0],rd(524)[0]]
        q['config']={}
        for a,n in ((0,125),(125,125),(250,125),(375,125),(1229,60)):
            q['config'].update({str(a+i):v for i,v in enumerate(rd(a,n))})
        q['config_changes']={a:[v,q['config'][a]] for a,v in prior['config_before'].items()
                             if v!=q['config'][a] and int(a) not in (167,373)}
        q['snapshots']=[]
        for _ in range(3):q['snapshots'].append(rt.snap(c));time.sleep(.4)
    finally:c.close()
    for board in test.BOARDS:
        sy=test.symbols(board)
        with rt.ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
                 options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target
            row=dict(board=board[0],output=list(t.read_memory_block8(*sy['output'])))
            memory=parse_hex(test.PACKAGE/(board[-1]+'.hex'));verified=0
            for lo,hi in blocks_of(memory):
                for addr in range(lo,hi,4096):
                    n=min(4096,hi-addr)
                    assert bytes(t.read_memory_block8(addr,n))==bytes(memory[addr+i] for i in range(n))
                    verified+=n
            row['verified_flash_bytes']=verified
            if board[0]!='330':
                p=sy['Parameter'][0]
                row['settings165_206']=[t.read16(p+2*a) for a in range(165,207)]
                row['globals']={a:t.read16(p+2*(200 if a=='365' else int(a))) for a in prior['global_original']}
                row['fault_layer']=t.read16(p+2*1501)
            for name in ('PSC316DefrostState','PSC316DefrostOwner'):
                if name in sy:row[name]=list(t.read_memory_block8(*sy[name]))
            q['boards'].append(row)
    q['source_mismatches']=[p for p,h in prior['source_inventory'].items() if rt.sha(test.ROOT/p)!=h]
    command="[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    output=subprocess.run(['pwsh','-NoProfile','-Command',command],capture_output=True,text=True,encoding='utf8',check=True).stdout
    processes=json.loads(output) if output.strip() else []
    if isinstance(processes,dict):processes=[processes]
    q['active_input_workers']=[p for p in processes if 'multiprocessing.spawn' in (p.get('CommandLine') or '') or ' -u tools/joint_v1056_remaining_' in (p.get('CommandLine') or '')]
    q['checks']=dict(versions=q['versions']==test.EXPECTED,bench=q['profile']==[3,15107],
        all_settings_restored=q['outdoor']==prior['outdoor_before'] and not q['config_changes']
            and q['shared']==prior['shared_before'] and q['switch']==prior['switch_before'],
        shared_vfd_original=q['new_shared']==prior['outdoor_before'][0][11:14],
        shared_type_original=q['shared_type']==prior['outdoor_before'][0][:2],
        globals_restored=q['globals']==prior['global_original'] and all(b['globals']==prior['global_original'] for b in q['boards'] if b['board']!='330'),
        actual_outdoor_settings=all(b['settings165_206']==prior['outdoor_before'][i] and b['fault_layer']==0 for i,b in enumerate(q['boards'][:2])),
        normal_stop=not any(q['commands']) and all(s['state'][9]==0 and rt.loads_off(s) for s in q['snapshots']),
        no_faults=all(not any(s['faults']) for s in q['snapshots']),
        board_outputs_off=all(not any(b['output']) for b in q['boards']),
        defrost_clear=all(not any(b.get('PSC316DefrostState',[])+b.get('PSC316DefrostOwner',[])) for b in q['boards']),
        source_unchanged=not q['source_mismatches'],no_input_workers=not q['active_input_workers'])
    q.update(passed=all(q['checks'].values()),finished=rt.now())
    path=test.DAY/('independent_audit_'+time.strftime('%H%M%S')+'.json');rt.dump(path,q)
    print(json.dumps(dict(evidence=str(path),passed=q['passed'],checks=q['checks']),ensure_ascii=False,indent=2))
    assert q['passed']

if __name__=='__main__':main()
