"""Public-register mode followups, with one serial writer and no debug port."""
from remaining_serial_only_live_20261106 import *


def loaded_modes():
    import remaining_loaded_modes_live_20261106 as checks
    checks.HeatBench=SerialHeatBench
    checks.main()


def normal_handoffs():
    b=SerialHeatBench('normal_mode_handoffs')
    try:
        pairs=[(s,t) for s in range(6) for t in range(6) if s!=t]
        ids={pair:f'T13-{11+i:03d}' for i,pair in enumerate(pairs)}
        route=(0,1,0,2,1,2,0)
        assert set(zip(route,route[1:]))=={(s,t) for s in range(3) for t in range(3) if s!=t}
        b.setup(0)
        b.config({128:0,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:320,161:150,315:0,320:0,346:0,245:1,247:0,
            329:2,330:0,331:1,335:1,336:1,337:1,338:1,
            323:5,324:5,325:0,328:30,132:30,135:30})
        b.temperature(0,250);b.reset_faults();b.start()

        def sample(label):
            s=b.snapshot(label)
            s.update(t=time.monotonic(),mode=b.rd(236)[0],special_phase=b.rd(885)[0])
            return s

        def ready(s,mode):
            return (s['mode']==mode and s['state'][9]==2 and s['state'][0]==4 and s['do'][3]==1 and s['do'][8]==1)

        def no_loads(s):
            return (all(s['ao'][i]==0 for i in (0,1,2,8,9)) and
                    all(v not in (2,3,4) for pair in s['outdoor_status'] for v in pair))

        began=time.monotonic()
        while not ready(sample('normal source ready'),0):
            assert time.monotonic()-began<60
            time.sleep(.15)
        for source,target in zip(route,route[1:]):
            cid=ids[source,target]
            initial=sample(cid+' source');assert ready(initial,source) and no_loads(initial),initial
            e=dict(passed=False,before=initial,source=source,target=target,edges=[],samples=[],
                scope='No thermal/humidity load; public shutdown then target startup; no private active/pending reads',
                physical_terminal_measurement=False)
            b.log['cases'][cid]=e;b.save()
            b.c.write_single_register(1,236,target)
            began=time.monotonic();last=None;last_report=began;exit_seen=False;stable_since=None
            while True:
                s=sample(cid);e['samples'].append(s)
                assert not any(s['faults']) and no_loads(s),s
                # Public mode write/readback alone does not prove a handoff.
                # Require an observed orderly exit stage, followed by stable
                # normal-running outputs and the target public mode register.
                exit_seen|=s['state'][9] in (0,1,3,4) or s['special_phase'] in (201,202,203)
                marker=(s['mode'],s['state'][0],s['state'][9],s['special_phase'],tuple(s['do']),tuple(s['ao']))
                if marker!=last:
                    e['edges'].append(dict(elapsed_s=time.monotonic()-began,sample=s));last=marker
                    b.save();print('SERIAL HANDOFF',cid,source,target,round(time.monotonic()-began,2),marker[:4],flush=True)
                if exit_seen and ready(s,target):
                    if stable_since is None:stable_since=time.monotonic()
                    if time.monotonic()-stable_since>=2:break
                else:stable_since=None
                assert time.monotonic()-began<240,(cid,'public mode handoff timeout',s)
                if time.monotonic()-last_report>=30:
                    b.save();print('SERIAL HANDOFF WAIT',cid,round(time.monotonic()-began,1),marker[:4],flush=True);last_report=time.monotonic()
                time.sleep(.12)
            e.update(passed=True,exit_seen=exit_seen,complete=s,duration_s=time.monotonic()-began)
            b.record_local(cid,True,f'无冷热湿负载，正常指令模式{source}→{target}；源模式送/排风先建立，实际采到正常退出步骤，随后目标模式寄存器、步骤2、正常运行及送/排风输出稳定2秒；全过程热湿AO为0且无压机运行反馈。复用前例已建立的目标作下一例源状态；仅公开寄存器，不据此宣称已读取私有活动/待切模式，物理端子及正式档未验。',e)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish();print('SERIAL NORMAL HANDOFFS RESTORED',b.log.get('restored'),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('actions',nargs='+',choices=('multifault','normal-handoffs','loaded-modes'))
    args=p.parse_args()
    for action in args.actions:
        try:
            if action=='multifault':
                from remaining_serial_multifault_20261106 import main
                main()
            elif action=='normal-handoffs':normal_handoffs()
            else:loaded_modes()
        except Exception:
            print('SERIAL FOLLOWUP ERROR',action,traceback.format_exc(),flush=True)
            latest=max(D.glob('remaining571_heat_dynamic_serial_*.json'),key=lambda p:p.stat().st_mtime)
            d=json.loads(latest.read_text('utf8'))
            if d.get('restored') is not True or d.get('cleanup_error'):raise
