"""Isolated targeted rerun; sequential hardware owner and flushed event records."""
import full_queue_context_20261113 as ctx
from full_queue_context_20261113 import *
import shutil
import os
import struct

DAY = R / '测试证据/缺口复测_20261113'
DAY.mkdir(parents=True, exist_ok=True)
ctx.DAY = DAY
ctx.runtime.D = DAY
ctx.runtime.RESULTS = DAY / 'case_results.json'
ctx.runtime.REPORT = DAY / 'progress.md'
for module in list(sys.modules.values()):
    if getattr(module, '__file__', '').startswith(str(R / 'tools')):
        for key in ('DAY', 'D'):
            if hasattr(module, key):
                setattr(module, key, DAY)
import joint_priority_20261110 as priority
priority.DAY = DAY
import joint_precondition_20261110 as precondition
precondition.DAY = DAY
import bench_current_20261112 as audit_module
audit_module.DAY = DAY
audit_module.I = I
audit_module.BOARDS = BOARDS


def event(kind, **data):
    row = dict(at=now(), t=time.monotonic(), kind=kind, **data)
    with (DAY / 'events.jsonl').open('a', encoding='utf8') as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
        f.flush()
    return row


class CapturedClient:
    def __init__(self, client, case):
        self.client, self.case = client, case

    def __getattr__(self, name):
        value = getattr(self.client, name)
        if not callable(value) or name not in (
                'read_holding_registers', 'write_single_register', 'write_multiple_registers'):
            return value
        def call(*args, **kwargs):
            started = time.monotonic()
            if name.startswith('write'):
                event('protocol_issue', case=self.case, operation=name, args=args, kwargs=kwargs)
            try:
                result = value(*args, **kwargs)
            except BaseException as exc:
                event('protocol_error', case=self.case, operation=name, args=args,
                      elapsed_s=time.monotonic()-started, error=repr(exc))
                raise
            event('protocol_response', case=self.case, operation=name, args=args,
                  result=result, started_t=started, elapsed_s=time.monotonic()-started)
            return result
        return call


Base = ctx.current_bench_class()


class Bench(Base):
    def __init__(self, name):
        super().__init__('rerun_' + name)
        old_path=self.path
        self.path=DAY/old_path.name
        if old_path!=self.path and old_path.exists():
            old_path.replace(self.path)
        self.c = CapturedClient(self.c, name)
        self.log['streamed_protocol_evidence'] = str((DAY / 'events.jsonl').relative_to(R))
        event('case_open', case=name, evidence=str(self.path))
        self.save()

    def snapshot(self, label):
        s = super().snapshot(label)
        event('snapshot', case=self.path.stem if hasattr(self, 'path') else '', label=label, sample=s)
        return s

    def wr(self, a, value):
        # Retry only after an independent read proves the idempotent setting
        # was not applied; preserve the original serial failure in the stream.
        try:
            return super().wr(a, value)
        except Exception:
            if a in (236, 524):
                raise
            if self.rd(a) == [value & 65535]:
                event('write_verified_after_exception', address=a, value=value)
                return
            raise

    def finish(self):
        # Engineering writes are allowed only while1300=1 and SysStep0.
        # Restore that block in its required order before base restoration.
        manual=sorted(a for a in self.touched if 1300<=a<=1318)
        if manual:
            self._cleaning_up=True
            assert self.rd(709)==[0], 'Manual restoration requires stopped330'
            self.c.write_single_register(1,1300,1)
            for a in manual:
                if a!=1300:self.c.write_single_register(1,a,self.original[str(a)])
            self.c.write_single_register(1,1300,self.original.get('1300',0))
            mismatches={a:[self.original[str(a)],self.rd(a)[0]] for a in manual
                        if self.rd(a)[0]!=self.original[str(a)]}
            self.log['manual_restore_mismatches']=mismatches
            assert not mismatches,mismatches
            self.touched.difference_update(manual)
            self.save()
        return super().finish()


def sample(b, label):
    s = dict(at=now(), t=time.monotonic(), label=label,
             selected_mode=b.rd(236)[0], effective_mode=b.rd(1)[0],
             state=b.rd(700,12), owner=b.extra[1][1].target.read8(b.extra[1][2]['PSC316DefrostOwner'][0]),
             boards=[])
    it=b.extra[1][1].target;isy=b.extra[1][2]
    for name in ('IndoorPendingWorkMode','IndoorActiveWorkMode'):
        a,n=isy[name];raw=bytes(it.read_memory_block8(a,n))
        s[name]=int.from_bytes(raw,'little',signed=name=='IndoorPendingWorkMode')
    for index, (t, sy) in enumerate(((b.ot,b.outsy),(b.extra[0][1].target,b.extra[0][2]))):
        p=sy['Parameter'][0]
        q=dict(output=list(t.read_memory_block8(*sy['output'])),
               phase=[t.read16(p+2*a) for a in (1420,1421)],
               alarms=list(struct.unpack('<28H',bytes(t.read_memory_block8(p+1200,56)))),
               mirror_phase=b.rd(1550+index*70,2), mirror_faults=b.rd(2022+index*128,28))
        for name in ('PSC316DefrostState','PSC316DefrostStateTime','SysHaveDef','CompRunTime'):
            a,n=sy[name]; raw=bytes(t.read_memory_block8(a,n))
            q[name]=list(struct.unpack('<'+'I'*(n//4),raw)) if name!='PSC316DefrostState' else list(raw)
        s['boards'].append(q)
    event('direct_and_mirror', sample=s)
    return s


def interruption(kind):
    b=Bench(kind)
    e=b.log['targeted_rerun']=dict(kind=kind,samples=[],scope='BENCH software/input evidence; no physical terminal or formal-time acceptance')
    try:
        b.prepare(); b.attach_extra()
        e['before']=sample(b,'active_defrost_before_'+kind)
        if kind=='whole_unit_disable':
            event('stimulus', case=kind, address=1832, value=1)
            b.gateway(1832,1)
        else:
            b.touched.add(236)
            event('stimulus', case=kind, address=236, value=2)
            # Deliberately bypass the old 3-second readback assertion. Record
            # request rejection/defer independently of lifecycle response.
            b.c.write_single_register(1,236,2)
        began=time.monotonic(); end=began+(360 if kind=='mode_during_defrost' else 65)
        while time.monotonic()<end:
            s=sample(b,kind);e['samples'].append(s)
            if kind=='whole_unit_disable':
                q=s['boards'][0]
                if q['PSC316DefrostState']==[0] and not any(q['SysHaveDef']) and s['owner']==0 and q['output'][:2]==[0,0] and all(x in (0,6) for x in q['phase']+q['mirror_phase']):
                    e.update(passed=True, final=s, conclusion='Lifecycle/owner released and compressors off; phase6 permitted while unit remains disabled')
                    break
            elif s['selected_mode']==2 and s['state'][9]==2 and s['owner']==0 and all(q['PSC316DefrostState']==[0] and q['output'][:2]==[0,0] for q in s['boards']):
                e.update(passed=True,final=s,conclusion='Mode request deferred through normal shutdown then applied as ventilation; lifecycle released')
                break
            time.sleep(.15)
        if kind=='mode_during_defrost':
            e['selected_mode_accepted']=any(s['selected_mode']==2 for s in e['samples'])
            e['observation']='Mode write and lifecycle captured without treating rejected/deferred command as a defrost failure'
            e['final']=e['samples'][-1]
        else:
            e.setdefault('passed',False)
        b.save();print('RERUN OBSERVATION',kind,e.get('passed'),e.get('selected_mode_accepted'),flush=True)
    except BaseException:
        e['error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:e['finished']=now();b.save();event('case_finished',case=kind,evidence=str(b.path),restored=b.log.get('restored'))


def initialize():
    bundle=DAY/'driver_snapshots'/time.strftime('%H%M%S')
    bundle.mkdir(parents=True,exist_ok=True)
    hashes={}
    for name in ('gap_capture_20261113.py','gap_cases_20261113.py','gap_report_20261113.py'):
        source=R/'tools'/name
        shutil.copy2(source,bundle/name)
        hashes[name]=ctx.runtime.sha(source)
    dump(bundle/'manifest.json',dict(at=now(),sha256=hashes))
    event('controller_driver_snapshot',directory=str(bundle.relative_to(R)),sha256=hashes)
    for p in (R/'测试证据/逐项测试_20261113').glob('recover_interrupted_v1058_*.json'):
        if not (DAY/p.name).exists():shutil.copy2(p,DAY/p.name)
    auth=DAY/'rerun_authorization.json'
    if not auth.exists():
        dump(auth,dict(at=now(),instructions=['再测一遍','认真抓取记录'],
            scope='Targeted gaps only; no automatic PRODUCTION queue or 2-hour soak'))
    for p in (R/'.codex-tmp/continuous_v1055_pause.request',R/'测试证据/逐项测试_20261113/hold_before_formal.request'):
        if p.exists():
            target=DAY/(p.name+'.archived_'+time.strftime('%H%M%S'))
            p.replace(target);event('previous_pause_archived',source=str(p),archive=str(target))


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('actions',nargs='+');args=p.parse_args()
    initialize()
    state=dict(pid=os.getpid(),started=now(),status='running',actions=[])
    journal=DAY/('controller_'+time.strftime('%H%M%S')+'.json');dump(journal,state)
    for action in args.actions:
        row=dict(action=action,started=now());state['actions'].append(row);dump(journal,state)
        try:
            if action=='preflight':audit_module.audit('preflight',True)
            elif action=='audit':audit_module.audit('independent_audit')
            elif action in ('whole_unit_disable','mode_during_defrost'):interruption(action)
            else:
                import gap_cases_20261113 as cases
                cases.run(action)
            row['status']='executed_see_evidence'
        except Exception:
            row.update(status='failed_or_condition_limited',error=traceback.format_exc())
            event('action_exception',**row)
        finally:
            row['finished']=now();dump(journal,state)
        # A failed action may continue only after independent restoration.
        if action not in ('preflight','audit'):
            try:audit_module.audit('after_'+action)
            except BaseException:
                state.update(status='recovery_failed',error=traceback.format_exc());dump(journal,state);raise
        elif row['status']!='executed_see_evidence':
            state['status']='preflight_failed';dump(journal,state);return
    state.update(status='targeted_queue_finished',finished=now());dump(journal,state)
    print('TARGETED CAPTURE QUEUE FINISHED',journal,flush=True)


if __name__=='__main__':
    # Helpers imported by spawned acquisition workers must not start a second
    # controller; the process main guard is also needed by multiprocessing.
    sys.modules['gap_capture_20261113']=sys.modules[__name__]
    main()
