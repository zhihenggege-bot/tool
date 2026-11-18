"""Current image binding, stopped recovery audit and sequential live dispatch."""
import joint_v1059_context_20261112 as ctx
from joint_v1059_context_20261112 import *
import argparse
import importlib

def audit(label, verify_image=False):
    from joint_precondition_20261110 import symbols
    from verify_board_flash_vs_hex import parse_hex, blocks_of
    p=DAY/(label+'_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),read_only=True,boards=[])
    manifest=json.loads((I/'manifest.json').read_text('utf8'))
    for name,want in manifest['source_inventory'].items():
        assert runtime.sha(R/name)==want,('Source no longer matches selected image',name)
    for name,want in manifest['artifacts'].items():
        assert runtime.sha(I/name)==want,('Selected artifact changed',name)
    q['source_inventory_matches']=len(manifest['source_inventory'])
    q['artifact_hashes_match']=True
    c=runtime.client()
    try:
        q['versions']=c.read_holding_registers(1,2622,18)
        assert q['versions']==runtime.EXPECTED
        q['profile']=c.read_holding_registers(1,1298,2)
        assert q['profile'][1]==15107
        q['snapshot']=runtime.snap(c)
        assert c.read_holding_registers(1,398,1)==[0]
        assert q['snapshot']['state'][9]==0 and loads_off(q['snapshot'])
        q['config']={}
        for a,n in [(0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2),(1319,26),(1389,11),(1830,96),(2680,98)]:
            q['config'].update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        recovery_files=sorted(DAY.glob('recover_interrupted_v1058_*.json'))
        if not recovery_files:
            recovery_files=sorted((R/'测试证据/台架执行_20261112').glob('recover_interrupted_v1058_*.json'))
        prior=json.loads(recovery_files[-1].read_text('utf8'))
        # [1] derives from mode; command398 stays stopped. Reset is a pulse.
        q['restoration_mismatches']={a:[v,q['config'].get(a)] for a,v in prior['original'].items()
            if int(a) not in (1,398,524) and a in q['config'] and q['config'][a]!=v}
        assert not q['restoration_mismatches'],q['restoration_mismatches']
        journals=[]
        for candidate in DAY.glob('*.json'):
            if candidate.name.startswith(('controller_','current_controller_')):continue
            try:
                data=json.loads(candidate.read_text('utf8'))
                if not isinstance(data,dict):continue
                if data.get('restored') and data.get('original'):journals.append((candidate,data))
            except (ValueError,OSError):continue
        if journals:
            latest,data=max(journals,key=lambda item:item[0].stat().st_mtime)
            q['latest_restored_case']=latest.name
            q['latest_case_readback_mismatches']={}
            for a,v in data['original'].items():
                if int(a) in (1,398,524):continue
                actual=c.read_holding_registers(1,int(a),1)[0]
                if actual!=v:q['latest_case_readback_mismatches'][a]=[v,actual]
            assert not q['latest_case_readback_mismatches'],q['latest_case_readback_mismatches']
        for board in BOARDS:
            sy=symbols(board)
            with ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
                t=ss.target;base=sy['Parameter'][0]
                row=dict(board=board[0],output=list(t.read_memory_block8(*sy['output'])))
                if board[0]!='330':
                    row['settings']=[t.read16(base+2*a) for a in range(165,207)]
                    row['alarms']=[t.read16(base+2*a) for a in range(600,628)]
                    row['phase']=[t.read16(base+2*a) for a in (1420,1421)]
                    assert not any(row['output'][i] for i in (0,1,2,3,4,5,7)),row
                    assert row['phase']==[0,0],row
                    if board[0]=='316_WJ1':
                        row['gateway_restore_mismatches']={a:[v,row['settings'][int(a)-1830]]
                            for a,v in prior.get('gateway_original',{}).items()
                            if row['settings'][int(a)-1830]!=v}
                        assert not row['gateway_restore_mismatches'],row
                if verify_image:
                    mem=parse_hex(I/(board[-1]+'.hex'))
                    for first,last in blocks_of(mem):
                        for addr in range(first,last,4096):
                            n=min(4096,last-addr)
                            assert bytes(t.read_memory_block8(addr,n))==bytes(mem[addr+i] for i in range(n)),(board[0],hex(addr))
                    row['flash_verified_bytes']=len(mem)
                q['boards'].append(row);dump(p,q)
        q.update(verified=True,finished=now());dump(p,q)
        print('INDEPENDENT AUDIT VERIFIED',p,flush=True)
        return q
    except BaseException:
        q['error']=traceback.format_exc();dump(p,q);raise
    finally:c.close()

def prepare():
    p=DAY/'preflight.json';assert not p.exists()
    m=json.loads((I/'manifest.json').read_text('utf8'))
    q=dict(at=now(),artifacts={},source_inventory={},profile='BENCH_ONLY_3S')
    for name,want in m['artifacts'].items():
        actual=runtime.sha(I/name);assert actual==want,(name,actual,want)
        q['artifacts'][name]=actual
    for name,want in m['source_inventory'].items():
        actual=runtime.sha(R/name);assert actual==want,('source differs from build',name)
        q['source_inventory'][name]=actual
    c=runtime.client()
    try:
        q['versions_before']=c.read_holding_registers(1,2622,18)
        assert q['versions_before']==[330,10,58,2026,11,10,316,12,40,2026,11,10,316,12,40,2026,11,10]
        q['snapshot']=runtime.snap(c)
        assert q['snapshot']['state'][9]==0 and loads_off(q['snapshot'])
        assert c.read_holding_registers(1,398,1)==[0]
        q['config']={}
        for a,n in [(0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2),(1319,26),(1389,11),(1830,96),(2680,98)]:
            q['config'].update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        dump(p,q)
    finally:c.close()
    for name in ('continuous_v1055_pause.request','fan_minrun_spotcheck_pause.request'):
        marker=R/'.codex-tmp'/name
        if marker.exists():
            target=DAY/(name+'.before_resume');assert not target.exists();marker.replace(target)
    dump(DAY/'resume_authorization.json',dict(at=now(),instruction='开始测试',scope='恢复后顺序执行剩余可测队列，问题留证，恢复核验后继续'))
    print('SOURCE/ARTIFACT BINDING VERIFIED',len(q['source_inventory']),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action');parser.add_argument('--value',type=int,default=30)
    a,legacy_args=parser.parse_known_args()
    if a.action!='legacy' and legacy_args:parser.error('Unexpected arguments: '+str(legacy_args))
    if a.action=='prepare':prepare();return
    if a.action=='restore':
        source=R/'测试证据/台架执行_20261111/remaining_heat_dispatch_4_184536.json'
        prior=json.loads(source.read_text('utf8'))
        b=current_bench_class()('post_flash_restore_exact_snapshot');b._cleaning_up=True
        b.original.update(prior['original']);b.touched.update(map(int,prior['original']))
        b.gateway_original.update({int(k):v for k,v in prior.get('gateway_original',{}).items()})
        b.log['restoration_source']=str(source.relative_to(R));b.save();b.finish()
        audit('post_flash_restore_audit',True);return
    if a.action=='flash':
        def record(case,status,actual,evidence,restored='',inputs=''):
            p=DAY/'deployment_results.json'
            data=json.loads(p.read_text('utf8')) if p.exists() else {}
            data[case]=dict(status=status,actual=actual,evidence=str(evidence),restored=restored,at=now());dump(p,data)
        runtime.result=record
        runtime.flash();audit('post_flash_audit',True);return
    if a.action=='audit':audit('independent_audit');return
    if a.action=='ntc':
        import bench_b01_ntc_20261111 as test
        test.run()
    elif a.action=='heat3':
        import bench_remaining_outdoor_20261111 as test
        test.heat_and_dispatch(3)
    elif a.action=='minrun':
        import bench_prestart_current_20261112 as test
        test.run(a.value,pairs=((2,4),),initial_hold_seconds=0,require_both=True)
    elif a.action=='typeII':
        import bench_typeII_regression_20261112 as test
        test.run()
    elif a.action=='coil-continuity':
        import bench_coil_continuity_20261112 as test
        test.run()
    elif a.action=='ntc0-diagnostics':
        import bench_ntc0_diagnostics_20261112 as test
        test.run()
    elif a.action=='vfd-curve':
        import bench_b03_fixed_vfd_20261111 as test
        pair={12:(1,2),22:(2,2),24:(2,4)}[a.value]
        test.run(pair)
    elif a.action=='ambient-history-gaps':
        import bench_b04_ambient_20261111 as test
        test.run(a.value)
    elif a.action=='natural-defrost-fin-exit':
        import bench_b05_normal_defrost_20261111 as test
        test.run()
    elif a.action in ('emergency','allocation'):
        import bench_extra_20261111 as test
        test.run(a.action)
    elif a.action=='soak':
        import continuous_followups_v1055_20261109 as test
        test.D=DAY;test.CheckedBench=current_bench_class()
        test.soak()
    elif a.action=='legacy':
        assert legacy_args and Path(legacy_args[0]).name.startswith('bench_remaining_')
        script=(R/legacy_args[0]).resolve();assert script.is_relative_to((R/'tools').resolve())
        rest=legacy_args[1:]
        # Import under its real module name so spawned acquisition workers
        # resolve the same bound context, instead of an unrelated __main__.
        test=importlib.import_module(script.stem)
        name=script.stem
        if name=='bench_remaining_adapter_20261111':test.run(rest[0])
        elif name=='bench_remaining_outdoor_20261111':
            if rest[0]=='heat':test.heat_and_dispatch(int(rest[1]))
            elif rest[0]=='ambient':test.ambient(rest[1])
            else:test.defrost_interrupt(rest[1])
        elif name=='bench_remaining_adc_20261111':
            (test.ventilation if rest[0]=='ventilation' else test.pressure_sensors)()
        elif name=='bench_remaining_defrost_analog_20261111':test.run(int(rest[0]))
        elif name=='bench_remaining_prestart_20261111':
            options=argparse.ArgumentParser();options.add_argument('--minimum-seconds',type=int,default=30)
            options.add_argument('--fixed-variable-only',action='store_true');options.add_argument('--measure-minrun',action='store_true')
            opts=options.parse_args(rest)
            test.run(opts.minimum_seconds,pairs=((2,4),) if opts.fixed_variable_only else None,
                initial_hold_seconds=0 if opts.measure_minrun else 11,require_both=opts.measure_minrun)
        elif name=='bench_remaining_da8_20261111':test.main()
        elif name in ('bench_remaining_defrost_matrix_20261111','bench_remaining_defrost_20261111','bench_remaining_rotation_20261111'):test.run(rest[0])
        else:
            assert not rest,rest
            test.run()
    else:raise ValueError(a.action)
    audit('after_'+a.action+'_audit')

if __name__=='__main__':main()
