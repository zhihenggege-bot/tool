"""Final source/image/configuration and save-cache audit after DA8 board tests."""
import json
import struct
import time
import traceback
from contextlib import ExitStack
import deploy_da8_manual_v1074_20261124 as dep


def main():
    d=dep.d;path=dep.DAY/'final_audit.json'
    assert not path.exists()
    tests=[json.loads((dep.DAY/(name+'.json')).read_text('utf8'))
        for name in ('board_manual','board_electric_separation')]
    assert all(t['passed'] and t['restored'] for t in tests)
    q=dict(started=d.now(),passed=False,boards=[],storage_samples=[])
    def save():dep.dump(path,q)
    try:
        c=d.client()
        with ExitStack() as stack:
            stack.callback(c.close)
            q['snapshot']=d.snap(c)
            assert d.stopped(q['snapshot']) and not any(q['snapshot']['594'])
            assert q['snapshot']['2622']==dep.EXPECTED
            actual=d.config(c)
            old=json.loads((dep.DAY/'deployment.json').read_text('utf8'))['config_before']
            ignored={1,167,373,1875,1923,1971,2019,259,1876,1924,1972,2020,245}
            q['configuration_differences']={a:[v,actual[a]] for a,v in old.items()
                if int(a) not in ignored and actual[a]!=v}
            q['intentional_migration']={'245':[old['245'],actual['245']]}
            assert not q['configuration_differences'] and actual['245']==1
            q['final_water_settings']={a:actual[a] for a in ('245','246','247','346')}
            contexts=[]
            for board in dep.BOARDS:
                image=dep.NEW if board[0]=='330' else board[6]
                ss=stack.enter_context(d.ConnectHelper.session_with_chosen_probe(
                    unique_id=board[1],target_override=board[2],options={
                    'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}))
                sy=d.symbols(image.with_suffix('.axf'));t=ss.target
                row=dict(name=board[0],verified_bytes=d.verify(t,image),
                    runtime=d.runtime(t,image.with_suffix('.axf')))
                assert row['runtime']==dict(recovery=300,profile=0,minimum_stop=120,minimum_run=180)
                if board[0]!='330':
                    pb,pd=t.read32(0x40010c0c),t.read32(0x4001140c)
                    row['gpio']=[(pb>>(12+i))&1 for i in range(4)]+[(pd>>(8+i))&1 for i in range(4)]
                    assert not any(row['gpio'])
                contexts.append((board[0],t,sy));q['boards'].append(row);save()
            began=time.monotonic()
            touched=set().union(*(
                {str(w['address']) for w in t['writes'] if 0<=w['address']<500 and w['address'] not in (1,167,373,398)}
                for t in tests))
            touched.add('245')
            while True:
                storage=[];pending=[]
                for name,t,sy in contexts:
                    values=list(struct.unpack('<500H',bytes(t.read_memory_block8(sy['Old_Parameter'],1000))))
                    entry=dict(board=name,write_error=t.read16(sy['CPURomWriteError']))
                    assert entry['write_error']==0
                    if name=='330':
                        entry.update(scalar_state=t.read8(sy['IndoorParameterSaveState']),
                            AI_dirty=t.read8(sy['IndoorAiCfgDirty']),AI_state=t.read8(sy['IndoorAiStState']),
                            saved_touched={a:values[int(a)] for a in sorted(touched,key=int)})
                        pending=[dict(address=a,saved=values[int(a)],actual=actual[a])
                            for a in touched if values[int(a)]!=actual[a]]
                    storage.append(entry)
                q['storage_samples'].append(dict(at=d.now(),boards=storage,pending=pending));save()
                if not pending and not any(r.get('scalar_state',0) or r.get('AI_dirty',0) or r.get('AI_state',0) for r in storage):break
                assert time.monotonic()-began<150,('Save-cache readiness',pending)
                time.sleep(1)
            manifest=json.loads((dep.OUT/'manifest.json').read_text('utf8'))
            q['source_inventory_matches']=dep.inventory()==manifest['source_inventory']
            q['artifact_hashes_match']=all(d.sha(dep.OUT/n)==h for n,h in manifest['artifacts'].items())
            old_manifest=json.loads((dep.OLD/'manifest.json').read_text('utf8'))
            q['changed_firmware_sources']=[name for name,value in manifest['source_inventory'].items()
                if old_manifest['source_inventory'].get(name)!=value]
            declared=json.loads((dep.DAY/'scope_and_artifacts.json').read_text('utf8'))['changed_sources']
            assert set(q['changed_firmware_sources'])==set(declared)
            assert q['source_inventory_matches'] and q['artifact_hashes_match']
            q.update(passed=True,finished=d.now(),save_cache_pending=[],physical_power_cycle_tested=False)
            save()
            manifest.update(hardware_tested=True,hardware_test_scope='DA8 manual/cold minimum/fault gates; software DA/PWM only',
                board_evidence=[str((dep.DAY/(name+'.json')).relative_to(dep.R))
                    for name in ('board_manual','board_electric_separation')])
            dep.dump(dep.OUT/'manifest.json',manifest)
        print('FINAL AUDIT PASS: firmware, baseline settings, stopped outputs and save cache match',flush=True)
    except BaseException:
        q.update(error=traceback.format_exc(),finished=d.now());save();raise


if __name__=='__main__':main()
