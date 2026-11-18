"""One serial writer; complete the missing special-mode abort stages in order.

Only ordinary configuration, DI polarity and on/off commands are written.
Special-mode waits use the real board clock. Each group restores configuration
before the next group. A pause file is checked without abandoning cleanup.
"""
from v1055_bench_context_20261109 import *
from remaining_pid_live_20261106 import *

PAUSE=R/'.codex-tmp/continuous_v1055_pause.request'

def paused():
    if PAUSE.exists():raise InterruptedError(PAUSE.read_text('utf8').strip() or 'Pause requested; normal cleanup follows')

GROUPS=[
    ('auto_transition_manual','T13-058',5,5,('manual',)),
    ('auto_exhaust_running','T13-057',5,4,('manual','fire')),
    ('disinfect_fan_wait','T13-048',3,2,('manual','fire')),
    ('auto_disinfect_fan_wait','T13-056',5,2,('manual','fire')),
    ('exhaust_fan_stagger','T13-052',4,2,('manual','fire')),
    ('disinfect_shutdown','T13-050',3,6,('manual','fire')),
    ('exhaust_shutdown','T13-054',4,6,('manual','fire')),
]

def sample(b,label):
    s=b.snapshot(label);s['special_diag']=b.rd(885,3);s['t']=time.monotonic()
    return s

def wait_stage(b,mode,stage,kind,entry):
    began=time.monotonic();last=None;last_print=began
    timeout=520 if mode==5 and stage==4 else 310
    while True:
        paused();s=sample(b,'establish '+str(stage));diag=s['special_diag']
        assert not any(s['faults']),s
        assert all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
        assert all(v not in (2,3,4) for pair in s['outdoor_status'] for v in pair),s
        if diag[0]!=last or time.monotonic()-last_print>=30:
            entry['edges'].append(s);b.save();last=diag[0];last_print=time.monotonic()
            print('STAGE WAIT',mode,stage,kind,round(time.monotonic()-began,1),diag,flush=True)
        count=diag[2] if stage==4 or mode==4 else diag[1]
        if stage==6:
            # Deliberately initiate an ordinary stop after a genuine active
            # stage; reverse/duplicate commands are separate tests below.
            if diag[0]==(4 if mode==4 else 3) and count>=6:
                b.wr(398,0)
                s=b.wait('ordinary special shutdown entered',lambda s:b.rd(885)[0]==6,8)
                s['special_diag']=b.rd(885,3);entry['shutdown_initiated_normally']=True
                return s
        elif diag[0]==stage and (stage not in (3,4) or count>=6):
            # Confirm outputs after the separate phase-register read; do not
            # classify a scan crossing as a persistent output mismatch.
            s=sample(b,'confirm stage '+str(stage));diag=s['special_diag']
            if diag[0]!=stage:continue
            if stage==5:
                if any(s['do'][i] for i in (3,8,10)):continue
                assert diag[1]>=60,(diag,s)
            elif stage==4:
                if not(s['do'][3] and s['do'][8] and not s['do'][10]):continue
                if mode==5:assert diag[1]>=60
            elif stage==2:
                if s['do'][10]:continue
                # Disinfection's20s gap has supply on, disinfect off;
                # exhaust uses a real3s BENCH stagger with one fan on.
                if mode in (3,5) and not s['do'][3]:continue
                if mode==4 and not(s['do'][3] or s['do'][8]):continue
            return s
        assert time.monotonic()-began<timeout,('stage unavailable',mode,stage,s)
        time.sleep(.15)

def group(name,cid,mode,stage,kinds):
    b=HeatBench('continuous_'+name)
    b.log['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    e=dict(passed=False,mode=mode,requested_stage=stage,runs=[],scope=name)
    b.log['cases'][cid]=e;b.save()
    try:
        for kind in kinds:
            paused();b.setup(mode)
            b.config({329:2,330:0,331:1,335:1,336:1,337:1,338:1,
                323:1,324:1,325:1,128:0,127:0,332:0,333:0,334:0,
                245:1,247:0,125:0,126:0,248:0,328:30 if mode==4 and stage==2 else 0})
            b.reset_faults();b.start()
            run=dict(kind=kind,passed=False,edges=[],requested_stage=stage);e['runs'].append(run);b.save()
            run['before']=wait_stage(b,mode,stage,kind,run)
            began=time.monotonic()
            if kind=='manual':b.wr(398,0)
            else:
                original=b.rd(156)[0];run['original_polarity']=original;b.wr(156,1-original)
            run['stopped']=b.wait('special stage abort clear',lambda s:s['state'][9]==0 and loads_off(s) and b.rd(885)[0]==0,60,kind=='fire')
            run['stop_observed_s']=time.monotonic()-began
            if kind=='fire':
                # For a short BENCH fan stagger or shutdown, the ordinary
                # sequencer can finish before the3s input debounce expires.
                # Observe the actual alarm too; don't mistake normal stop for
                # proof that the fire input has already been qualified.
                b.wait('fire qualified and latched',lambda s:b.rd(605)[0]==1 and s['state'][9]==0 and loads_off(s),6,True)
                run['fire_latched']=sample(b,'fire latch confirmed')
                b.wr(156,original);time.sleep(.5);assert b.rd(605)[0]==1;b.reset_faults()
            hold=time.monotonic();run['hold_samples']=[]
            while time.monotonic()-hold<10:
                paused();s=sample(b,'abort holds stopped');run['hold_samples'].append(s)
                assert s['state'][9]==0 and loads_off(s) and s['special_diag'][0]==0 and not any(s['faults']),s
                time.sleep(.25)
            b.start();run['restart_diag']=b.rd(885,3);assert run['restart_diag']==[1,0,0]
            b.stop();run.update(passed=True,finished=now());b.save()
            print('STAGE ABORT PASS',cid,mode,stage,kind,flush=True)
        e['passed']=True
        b.record_local(cid,True,f'V10.55连续补测{name}：模式{mode}实际到达阶段{stage}，'+('/'.join(kinds))+'中止后主步骤、[885]及负载软件输出清零；消防按真实3秒DI滤波并另核对锁存；停后观察10秒无重启，新开机[885..887]=[1,0,0]。所有专用等待真实计时，未改计时/需求/输出RAM。仅该阶段子范围，物理接点/端子和正式时序另验。',e)
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish();print('GROUP RESTORED',name,b.log.get('restored'),flush=True)
    return b.path

def main():
    journal=D/('continuous_special_queue_20261109_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),single_writer=True,pause_file=PAUSE.relative_to(R).as_posix(),groups=[])
    dump(journal,q)
    for name,cid,mode,stage,kinds in GROUPS:
        row=dict(name=name,id=cid,mode=mode,stage=stage,started=now(),status='running');q['groups'].append(row);dump(journal,q)
        try:
            evidence=group(name,cid,mode,stage,kinds)
            row.update(status='completed',evidence=evidence.relative_to(R).as_posix())
        except InterruptedError:
            row.update(status='paused',error=traceback.format_exc());dump(journal,q);return
        except Exception:
            row.update(status='failed_or_unavailable',error=traceback.format_exc());dump(journal,q)
            # Only continue after the group's own finally proved recovery.
            latest=max(D.glob('remaining571_heat_dynamic_continuous_'+name+'*.json'),key=lambda p:p.stat().st_mtime)
            recovery=json.loads(latest.read_text('utf8'))
            if not recovery.get('restored') or recovery.get('cleanup_error'):raise
        row['finished']=now();dump(journal,q)
    q['finished']=now();dump(journal,q);print('SPECIAL QUEUE COMPLETE',journal,flush=True)

if __name__=='__main__':main()
