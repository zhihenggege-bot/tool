"""Independent read-only audit against each setting's first saved value today."""
from joint_precondition_20261110 import *


def main():
    dest=DAY/('final_independent_readback_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),read_only=True,expected={},references={},samples=[],boards=[])
    journals=[]
    for path in DAY.glob('*.json'):
        try:
            j=json.loads(path.read_text('utf8'))
        except (ValueError,OSError):continue
        if 'original' in j and 'started' in j:journals.append((j['started'],path,j))
    for _,path,j in sorted(journals,key=lambda x:x[0]):
        for a,v in j['original'].items():
            if int(a) in (1,398,524):continue
            if a not in q['expected']:
                q['expected'][a]=v;q['references'][a]=path.name
        for a,v in j.get('gateway_original',{}).items():
            a=str(a)
            if a not in q['expected']:
                q['expected'][a]=v;q['references'][a]=path.name
        for event in j.get('gateway_writes',[]):
            # Gateway helpers store the initial value separately only in some
            # journals. Never invent an initial value from the requested value.
            a=str(event['address'])
            if 'before' in event and a not in q['expected']:
                q['expected'][a]=event['before'];q['references'][a]=path.name
    c=runtime.client()
    try:
        q['versions']=c.read_holding_registers(1,2622,18)
        q['profile']=c.read_holding_registers(1,1298,2)
        q['actual']={a:c.read_holding_registers(1,int(a),1)[0] for a in q['expected']}
        q['mismatches']={a:dict(before=v,after=q['actual'][a]) for a,v in q['expected'].items() if q['actual'][a]!=v}
        q['command_inputs']={str(a):c.read_holding_registers(1,a,1)[0] for a in (398,524)}
        q['extra_faults']={str(a):c.read_holding_registers(1,a,1)[0] for a in (627,911,912,913,924,956,958,960,962,964,966,968)}
        for _ in range(3):q['samples'].append(runtime.snap(c));time.sleep(.4)
    finally:c.close()
    for board in BOARDS:
        sy=symbols(board)
        with ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target;p=sy['Parameter'][0]
            row=dict(name=board[0],uptime_ms=t.read32(sy['Systick_1ms'][0]),output=list(t.read_memory_block8(sy['output'][0],sy['output'][1])))
            indexes=(1550,1551,1620,1621) if board[0]=='330' else (1400,1403,1420,1421,1501)
            row['params']={str(a):t.read16(p+a*2) for a in indexes}
            for key in ('PSC316DefrostState','PSC316DefrostOwner'):
                if key in sy:
                    a,n=sy[key];row[key]=list(t.read_memory_block8(a,n))
            q['boards'].append(row)
    inventory=json.loads((R/'.codex-tmp/special_display_v1055_v1239_20261109/source_change_manifest.json').read_text('utf8'))['source_inventory_after']
    q['source_count']=len(inventory)
    q['source_mismatches']=[p for p,want in inventory.items() if hashlib.sha256((R/p).read_bytes()).hexdigest()!=want]
    # Record test workers rather than inferring their exit from output state.
    import subprocess
    cmd="Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' } | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    proc=subprocess.run(['pwsh','-NoProfile','-Command',cmd],capture_output=True,text=True,encoding='utf8',check=True)
    workers=json.loads(proc.stdout) if proc.stdout.strip() else []
    if isinstance(workers,dict):workers=[workers]
    q['python_processes']=workers
    q['active_input_workers']=[w for w in workers if 'multiprocessing.spawn' in (w.get('CommandLine') or '') or ('joint_' in (w.get('CommandLine') or '') and 'joint_final_readback_20261110.py' not in w['CommandLine'])]
    q['checks']=dict(settings_restored=not q['mismatches'],commands_off=not any(q['command_inputs'].values()),versions_expected=q['versions']==runtime.EXPECTED,
        bench_profile=q['profile']==[3,15107],loads_stopped=all(s['state'][9]==0 and loads_off(s) for s in q['samples']),
        no_faults=not any(q['extra_faults'].values()) and all(not any(s['faults']) for s in q['samples']),
        all_board_outputs_off=all(not any(r['output']) for r in q['boards']),
        defrost_lifecycle_clear=all(not any(r.get('PSC316DefrostState',[])+r.get('PSC316DefrostOwner',[])) for r in q['boards']),
        firmware_sources_unchanged=not q['source_mismatches'],no_active_test_input_workers=not q['active_input_workers'])
    q.update(finished=now(),passed=all(q['checks'].values()));dump(dest,q)
    print(json.dumps(dict(evidence=str(dest),checks=q['checks'],mismatches=q['mismatches']),ensure_ascii=False,indent=2))
    assert q['passed'],q['checks']


if __name__=='__main__':main()
