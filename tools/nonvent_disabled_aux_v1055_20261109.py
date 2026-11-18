"""Disabled equipment allocation and auxiliary-heat eligibility, live board.

Normal 330-to-316 gateway only, destination readback via exact-image SWD.
No compressor/runtime/demand/thermal-output/PID/timer state injection.
"""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench,paused
from nonvent_supplement_v1055_20261109 import restored_latest
import subprocess,sys


def run(disable_unit):
    b=CheckedBench('disabled_aux_unit' if disable_unit else 'disabled_aux_comp');ss=None;original={}
    a=1832 if disable_unit else 1833;want=2 if disable_unit else 3
    ids=['T10-015','T11-088'] if disable_unit else ['T11-087']
    e=dict(passed=False,disable_address=a,expected_available_count=want,phases=[],
        stimulus='Normal 330 gateway disable, room temperature and real PID scans',
        scope='Two installed outdoor units; disabled equipment excluded and remaining all-full auxiliary permission; no physical power or formal timing')
    for cid in ids:b.log['cases'][cid]=e
    b.save()
    try:
        from elftools.elf.elffile import ELFFile
        with (I/(BOARDS[0][-1]+'.axf')).open('rb') as f:
            outsy={s.name:(s['st_value'],s['st_size']) for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols() if s.name}
        ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();ot=ss.target
        def gateway(addr,value):
            if addr not in original:original[addr]=b.rd(addr)[0]
            state=1830+((addr-1830)//48)*48+43;began=time.monotonic()
            while b.rd(state)[0]==1:
                assert time.monotonic()-began<45,('gateway busy',addr);time.sleep(.2)
            if b.rd(addr)[0]!=value:
                b.c.write_single_register(1,addr,value);began=time.monotonic()
                while not(b.rd(addr)[0]==value and b.rd(state)[0]!=1):
                    assert time.monotonic()-began<50,('gateway verify',addr,value,b.rd(addr)[0],b.rd(state)[0]);time.sleep(.2)
            target=165+(addr-1830)%48
            actual=ot.read16(outsy['Parameter'][0]+target*2)
            assert actual==value,('gateway destination',addr,target,value,actual)
            b.log.setdefault('gateway_operations',[]).append(dict(address=addr,value=value,destination_register=target,destination_value=actual,at=now()));b.save()
        def sample(label):
            s=b.snapshot(label);s.update(actual_count=b.rd(119)[0],aux_demand=b.rd(890)[0],
                target_count=b.rd(881)[0],installed_count=b.rd(2678)[0],
                destination_comp=list(ot.read_memory_block8(outsy['Comp'][0],2)))
            return s
        def disabled_off(s):return s['destination_comp'][0]==0 and (not disable_unit or s['destination_comp'][1]==0)
        def observe(label,seconds,predicate):
            p=dict(label=label,samples=[]);e['phases'].append(p);began=time.monotonic();heartbeat=began
            while time.monotonic()-began<seconds:
                paused();s=sample(label);p['samples'].append(s);assert predicate(s),s
                if time.monotonic()-heartbeat>=20:
                    print('DISABLED AUX',label,round(time.monotonic()-began,1),s['actual_count'],s['aux_demand'],s['destination_comp'],flush=True);heartbeat=time.monotonic();b.save()
                time.sleep(.2)
            p['observed_s']=time.monotonic()-began;b.save();return p
        b.setup(1);gateway(a,1)
        b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,426:100,427:1,428:0,
            347:100,348:1,349:0,315:0,327:1,320:0,346:0,
            329:2,330:0,331:0,245:1,247:0,365:1,10:500,12:500})
        b.temperature(0,220);b.reset_faults();b.start();began=time.monotonic();p=dict(label='actual loading with disabled equipment',samples=[]);e['phases'].append(p);heartbeat=began
        while True:
            paused();s=sample(p['label']);p['samples'].append(s)
            assert disabled_off(s) and not any(s['faults']),s
            running=[v for pair in s['outdoor_status'] for v in pair if v==3]
            # Auxiliary may only rise once every remaining available compressor
            # actually reports heat operation, independent of installed CN.
            if len(running)<want:assert s['aux_demand']==0 and s['ao'][0]==0,s
            if len(running)==want and s['actual_count']==want and s['aux_demand']==1000 and s['ao'][0]==1000:break
            assert time.monotonic()-began<190,('disabled auxiliary loading incomplete',s)
            if time.monotonic()-heartbeat>=20:
                print('DISABLED AUX LOAD',a,round(time.monotonic()-began,1),s['outdoor_status'],s['aux_demand'],flush=True);heartbeat=time.monotonic();b.save()
            time.sleep(.15)
        e['full']=s
        observe('remaining available equipment full allows auxiliary',8,
            # Register119 is an asynchronously refreshed display. The full
            # eligibility assertion uses each circuit's actual feedback;
            # retain119 samples and quantify convergence separately below.
            lambda s:disabled_off(s) and sum(v==3 for pair in s['outdoor_status'] for v in pair)==want and s['aux_demand']==s['ao'][0]==1000 and s['installed_count']==4 and not any(s['faults']))
        rows=e['phases'][-1]['samples']
        e['running_count_readback_mismatches']=[s for s in rows if s['actual_count']!=want]
        e['running_count_display_scope']='119 retained as asynchronous diagnostic; not qualified as exact per-sample count in this eligibility subtest'
        # After this established full state, remove heat demand via genuine
        # legal input and wait for actual unload before checking heat remains0.
        b.temperature(0,280);began=time.monotonic();p=dict(label='room warm unloads actual compressors',samples=[]);e['phases'].append(p)
        while True:
            paused();s=sample(p['label']);p['samples'].append(s);assert disabled_off(s) and not any(s['faults']),s
            if s['actual_count']==0 and all(v not in (2,3,4) for pair in s['outdoor_status'] for v in pair) and s['aux_demand']==s['ao'][0]==0:break
            assert time.monotonic()-began<150,('normal heat unload incomplete',s)
            time.sleep(.2)
        observe('available but nonrunning equipment cannot allow auxiliary',4,
            lambda s:disabled_off(s) and s['actual_count']==s['aux_demand']==s['ao'][0]==0)
        b.stop();gateway(a,original[a]);b.log['gateway_restored']={str(x):b.rd(x)[0]==v for x,v in original.items()};assert all(b.log['gateway_restored'].values())
        e['passed']=True;b.save()
        text=f'V10.55经330→316正常网关[{a}]=1禁用'+('外机1' if disable_unit else '外机1压机1')+f'，目的板参数回读确认；压机动力隔离，剩余{want}台实际制热反馈全建立前辅热保持0，全部运行后真实PID辅热达1000并保持8s，安装CN仍4；禁用设备Comp软件输出始终0。合法室温升到28℃后实际卸载，未运行时辅热清0并保持。寄存器119异步数量显示有{len(e["running_count_readback_mismatches"])}个与逐回路反馈不一致样本，原样保留，不判显示完整通过。网关与参数恢复；不是实际端子/正式秒数验收。'
        for cid in ids:b.record_local(cid,True,text,e)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:
        try:
            b.stop()
            if ss:
                for addr,value in original.items():gateway(addr,value)
                b.log['gateway_restored']={str(x):b.rd(x)[0]==v for x,v in original.items()};assert all(b.log['gateway_restored'].values());b.save()
        except BaseException:b.log['cleanup_error']=traceback.format_exc();b.save();raise
        finally:
            if ss:ss.close()
            b.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True)
    p.add_argument('--kinds',nargs='+',choices=('comp','unit'),default=('comp','unit'));a=p.parse_args()
    dep=a.after.resolve();journal=D/('nonvent_disabled_aux_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),dependency=dep.relative_to(R).as_posix(),status='waiting_without_hardware',actions=[],ventilation='Deferred by user');dump(journal,q)
    while True:
        paused()
        try:previous=json.loads(dep.read_text('utf8'))
        except (OSError,ValueError):previous={}
        if previous.get('finished'):break
        time.sleep(3)
    assert previous.get('status')=='completed',previous
    restored_latest();q['status']='running';dump(journal,q)
    try:
        for disable_unit in (key=='unit' for key in a.kinds):
            paused();restored_latest();row=dict(disable_unit=disable_unit,started=now(),status='running');q['actions'].append(row);dump(journal,q)
            try:run(disable_unit);row['status']='finished_see_per_case_scope'
            except Exception:
                row.update(status='failed_or_unavailable',error=traceback.format_exc());dump(journal,q);restored_latest()
            row['finished']=now();dump(journal,q)
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=300)
            q['actions'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(journal,q)
            assert proc.returncode==0,(script,proc.stderr)
        q['status']='completed'
    finally:q['finished']=now();dump(journal,q)
    print('NONVENT DISABLED AUX FINISHED',journal,flush=True)


if __name__=='__main__':main()
