"""Run the V10.58 B01 NTC subset through normal heat demand and ADC inputs."""
from joint_v1058_context_20261111 import *
from joint_outdoor_ntc_protection_20261110 import worker
import multiprocessing as mp
import queue


CASES = [('O-PROTECT-003',3,615,0), ('O-PROTECT-004',5,617,0),
         ('O-PROTECT-005',1,613,0), ('O-PROTECT-016',0,612,None),
         ('O-PROTECT-008',4,616,1), ('O-PROTECT-009',6,618,1),
         ('O-PROTECT-010',2,614,1)]


def fixture(board, sy, values, stop, stream):
    stream.cancel_join_thread()
    worker(board, sy, values, stop, stream)


def run(recheck=False):
    b = current_bench_class()('NTC0_peer_control_diagnostics')
    e = b.log['B01'] = dict(cases=[], scope='Normal 330 heat demand; 316 #1 raw NTC input, software outputs and alarms; no physical contact or production timing evidence')
    proc = None
    try:
        assert b.rd(398)==[0] and b.rd(709)==[0] and not any(b.rd(2598,2))
        b.setup(1)
        b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,
                  315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,
                  428:0,347:100,348:1,349:0,346:0,320:0,245:1,247:0,
                  329:2,330:0,331:0,365:1,372:350,10:500,12:500})
        b.temperature(0,220)
        b.start()
        b.wait('330 heating demand and four systems running',
               lambda s:all(v==3 for p in s['outdoor_status'] for v in p),180)
        b.attach_extra()
        _, indoor, indoor_sy = b.extra[1]
        poll_addr = indoor_sy['PSC316PollRound'][0]
        b.outss.close(); b.outss = None
        ctx = mp.get_context('spawn')
        values, stop, stream = ctx.Array('i',[-1]*8), ctx.Event(), ctx.Queue()
        proc = ctx.Process(target=fixture,args=(BOARDS[0],b.outsy,values,stop,stream),daemon=True)
        proc.start()
        kind, message = stream.get(timeout=25)
        assert kind == 'ready', (kind,message)

        def apply(ch=None):
            with values.get_lock():
                values[:] = [0 if i == ch else -1 for i in range(8)]
            return time.monotonic()

        def observe(row,label,after,seconds,predicate):
            end = time.monotonic()+seconds
            samples = row.setdefault(label,[])
            while time.monotonic()<end:
                try: kind,s = stream.get(timeout=min(2,max(.01,end-time.monotonic())))
                except queue.Empty:
                    if not proc.is_alive(): raise RuntimeError('fixture exited')
                    continue
                if kind=='error': raise RuntimeError(s)
                if kind!='sample' or s['t']<after: continue
                if time.monotonic()-s['t']>1.5: continue
                s.update(read330_t=time.monotonic(), mirror=b.rd(2022,28),
                         layer=b.rd(2598,2), latch=b.rd(2618,2), comm=b.rd(594,2),
                         other=b.rd(1625,2), poll=indoor.target.read8(poll_addr))
                s.update(target330=b.rd(881)[0], environment_state330=b.rd(882)[0], selected_page330=b.rd(540)[0],
                         faultwords330=b.rd(630,3), peer_layer330=b.rd(2599)[0])
                if 'EnviOFFfalg' in indoor_sy:s['global_environment_off']=indoor.target.read8(indoor_sy['EnviOFFfalg'][0])
                s['requests330']={str(a):b.rd(a)[0] for a in (10,12,315,327)}
                samples.append(s)
                if predicate(s,samples): return s
            raise TimeoutError(label)

        selected = [c for c in CASES if c[0]=='O-PROTECT-016']
        e.update(recheck=recheck, hold_limit_s=240 if recheck else 60)
        for cid,ch,alarm,system in selected:
            r = dict(id=cid,channel=ch,alarm=alarm,started=now())
            e['cases'].append(r); b.save(); print('B01 START',cid,flush=True)
            offset = alarm-600
            applied = False
            try:
                observe(r,'healthy',time.monotonic(),210,
                        lambda s,_:s['output'][:2]==[1,1] and not any(s['alarms']) and not any(s['mirror']))
                applied = True
                at = apply(ch)
                edge = observe(r,'source_edge',at,35,lambda s,_:s['alarms'][offset]==1)
                protected = [0,0] if system is None else ([0,1] if system==0 else [1,0])

                def held(s,rows):
                    changes = sum(a['poll']!=z['poll'] for a,z in zip(rows,rows[1:]))
                    return changes>=12 and s['t']-rows[0]['t']>=10

                try: observe(r,'hold',edge['t'],240 if recheck else 60,held)
                except TimeoutError: r['hold_window_timeout'] = True
                samples = r.get('hold',[])
                stable = [s for s in samples if s['alarms'][offset]==1]
                r.update(source_dropout=len(samples)-len(stable),
                         protection_seen=any(s['output'][:2]==protected for s in stable),
                         peer_continues=bool(stable) and all(s['other']==[3,3] for s in stable),
                         mirror_seen=any(s['mirror'][offset]==1 for s in stable),
                         layer_seen=any(s['layer'][0]==s['params']['1501'] and s['layer'][0]&31 for s in stable),
                         latch_seen=any(s['latch'][0]&31 for s in stable),
                         poll_round_changes=sum(a['poll']!=z['poll'] for a,z in zip(samples,samples[1:])))
                r['status'] = ('软件子范围通过' if stable and not r['source_dropout'] and not r.get('hold_window_timeout')
                               and all(r[k] for k in ('protection_seen','peer_continues','mirror_seen','layer_seen','latch_seen'))
                               else '实测有待核对')
            except Exception as exc:
                r.update(status='实测条件未建立或采样异常',error=repr(exc))
            finally:
                removed = apply()
                try:
                    recovered = observe(r,'recovery',removed,180 if recheck else 55,lambda s,_:not any(s['alarms'])
                                        and not any(s['mirror']) and not (s['params']['1501']&31)
                                        and not (s['layer'][0]&31))
                    r['recovery_verified'] = True
                    r['latch_after_recovery'] = recovered['latch'][0]
                except Exception as exc:
                    r.update(recovery_verified=False,recovery_error=repr(exc))
                r.update(finished=now(),stimulus_requested=applied); b.save()
                print('B01 DONE',cid,r['status'],'restored',r['recovery_verified'],flush=True)
            if not r['recovery_verified']:
                e['blocked'] = 'NTC/alarm recovery not verified; stop affected tests and restore stopped baseline'
                break
    except BaseException:
        e['execution_error'] = traceback.format_exc(); b.save(); raise
    finally:
        try:
            if proc is not None:
                with values.get_lock(): values[:] = [-1]*8
                stop.set()
                proc.join(8)
                if proc.is_alive():
                    proc.terminate(); proc.join(3)
                    e['fixture_forced_exit'] = True
                e['fixture_exitcode'] = proc.exitcode
                stream.close()
        finally:
            try:
                if b.outss is None:
                    b.outss = ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
                        options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
                    b.outss.open(); b.ot = b.outss.target
                b.finish()
            finally:
                e['finished'] = now(); b.save(); print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--recheck',action='store_true')
    run(parser.parse_args().recheck)
