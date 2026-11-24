"""Verify standby water output while every other actuator is stopped."""
import json
import struct
import time
import traceback
from contextlib import ExitStack
import build_da8_standby_v1075_20261124 as build
import deploy_da8_standby_v1075_20261124 as deploy


def main():
    dep=deploy.configure();d=dep.d;day=build.DAY
    path=day/'final_audit.json';assert not path.exists()
    candidates=[json.loads(p.read_text('utf8')) for p in day.glob('board_standby*.json')]
    image_hash=d.sha(dep.NEW.with_suffix('.axf'))
    tests=[q for q in candidates if q.get('passed') and q.get('restored') and q.get('image_sha256')==image_hash]
    assert tests,'No completed and restored board verification'
    q=dict(started=d.now(),passed=False,boards=[],save_samples=[])
    def save():dep.dump(path,q)
    try:
        c=d.client()
        with ExitStack() as stack:
            stack.callback(c.close)
            q['snapshot']=d.snap(c)
            assert deploy.standby(q['snapshot']) and not any(q['snapshot']['594'])
            assert q['snapshot']['2622']==dep.EXPECTED
            actual=d.config(c);before=json.loads((day/'deployment.json').read_text('utf8'))['config_before']
            ignored={1,167,373,1875,1923,1971,2019,259,1876,1924,1972,2020}
            q['config_differences']={a:[v,actual[a]] for a,v in before.items()
                if int(a) not in ignored and actual[a]!=v}
            assert not q['config_differences'],q['config_differences']
            contexts=[]
            for board in dep.BOARDS:
                image=dep.NEW if board[0]=='330' else board[6]
                ss=stack.enter_context(d.ConnectHelper.session_with_chosen_probe(
                    unique_id=board[1],target_override=board[2],options={
                    'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}))
                t=ss.target;sy=d.symbols(image.with_suffix('.axf'))
                row=dict(board=board[0],verified_bytes=d.verify(t,image),runtime=d.runtime(t,image.with_suffix('.axf')))
                assert row['runtime']==dict(recovery=300,profile=0,minimum_stop=120,minimum_run=180)
                if board[0]!='330':
                    pb,pd=t.read32(0x40010c0c),t.read32(0x4001140c)
                    row['gpio']=[(pb>>(12+i))&1 for i in range(4)]+[(pd>>(8+i))&1 for i in range(4)]
                    assert not any(row['gpio'])
                contexts.append((board[0],t,sy));q['boards'].append(row);save()
            touched={str(w['address']) for test in tests for w in test['writes']
                if 0<=w['address']<500 and w['address'] not in (1,167,373,398)}
            touched|={'245','247','346'}
            began=time.monotonic()
            while True:
                storage=[];pending=[]
                for name,t,sy in contexts:
                    row=dict(board=name,write_error=t.read16(sy['CPURomWriteError']))
                    assert row['write_error']==0
                    if name=='330':
                        saved=list(struct.unpack('<500H',bytes(t.read_memory_block8(sy['Old_Parameter'],1000))))
                        row.update(scalar_state=t.read8(sy['IndoorParameterSaveState']),
                            AI_dirty=t.read8(sy['IndoorAiCfgDirty']),AI_state=t.read8(sy['IndoorAiStState']),
                            saved_values={a:saved[int(a)] for a in sorted(touched,key=int)})
                        pending=[dict(address=a,saved=saved[int(a)],actual=actual[a])
                            for a in touched if saved[int(a)]!=actual[a]]
                    storage.append(row)
                q['save_samples'].append(dict(at=d.now(),storage=storage,pending=pending));save()
                if not pending and not any(r.get('scalar_state',0) or r.get('AI_dirty',0) or r.get('AI_state',0) for r in storage):break
                assert time.monotonic()-began<150,pending
                time.sleep(1)
            # Verify the physical probe restored after raw input simulation; DA8
            # may be energized while the entire remaining machine is stopped.
            fresh=c.read_holding_registers(1,512,1)[0];fresh=fresh-65536 if fresh>=32768 else fresh
            minimum=actual['346'];expected=minimum if fresh<0 else 0
            q['final_water']=dict(fresh10=fresh,manual=actual['247'],minimum=minimum,
                display=c.read_holding_registers(1,925,1)[0],final=c.read_holding_registers(1,922,1)[0])
            name,t,sy=contexts[2]
            q['final_water']['pwm']=t.read32(0x4000043c)&65535
            assert q['final_water']['display']==q['final_water']['final']==expected
            assert q['final_water']['pwm']==expected*98//100
            manifest=json.loads((dep.OUT/'manifest.json').read_text('utf8'))
            old=json.loads((build.OLD/'manifest.json').read_text('utf8'))
            q['changed_sources']=[n for n,h in manifest['source_inventory'].items() if old['source_inventory'].get(n)!=h]
            assert set(q['changed_sources'])=={
                'PSC330RK-V10-内机/User/UserSrc/UserAction.c',
                'PSC330RK-V10-内机/User/UserSrc/ErrorCheck.c',
                'PSC330RK-V10-内机/User/UserHead/User.h'}
            assert build.inventory()==manifest['source_inventory']
            assert all(d.sha(dep.OUT/n)==h for n,h in manifest['artifacts'].items())
            q.update(passed=True,finished=d.now(),physical_terminal_measured=False,physical_power_cycle_tested=False)
            save()
            manifest.update(hardware_tested=True,board_evidence='final_audit.json',
                hardware_test_scope='normal standby frost,0C boundary,disabled minimum,normal stop,probe fault; DA/PWM only')
            dep.dump(dep.OUT/'manifest.json',manifest)
        print('FINAL STANDBY AUDIT PASS',q['final_water'],flush=True)
    except BaseException:
        q.update(error=traceback.format_exc(),finished=d.now());save();raise


if __name__=='__main__':main()
