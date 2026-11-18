"""Additional current-image bench scopes; no firmware/timer/output writes."""
from joint_v1056_context_20261110 import *
import multiprocessing as mp
import queue
from joint_outdoor_ntc_protection_20261110 import worker

CurrentBench = current_bench_class()
PAIRS = ((0,0),(0,1),(1,2),(1,3),(2,2),(2,4))


def disable(pair_index):
    import joint_outdoor_disable_20261110 as test
    pair = PAIRS[pair_index]

    class PairBench(CurrentBench):
        def setup(self, *args, **kwargs):
            super().setup(*args, **kwargs)
            self.gateway(1830, pair[0])
            self.gateway(1831, pair[1])

    test.TodayBench = PairBench
    test.run()


def continuity():
    import joint_coil_continuity_20261110 as test
    test.TodayBench = CurrentBench
    test.run()


def mirrors():
    b = CurrentBench('outdoor_NTC_mirror_streaming_recheck')
    e = dict(started=now(), cases=[], input_events=[], samples=[], status='running',
             scope='Normal indoor heat start; raw NTC inputs only; continuous fresh316 diagnostics together with330 mirrors, no alarm/state/timer forcing; not physical disconnect evidence.')
    b.log['mirror_recheck'] = e
    proc = stop = values = None
    out = None
    try:
        b.setup(1)
        b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,
                  315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,
                  428:0,347:100,348:1,349:0,346:0,320:0,245:1,247:0,
                  329:2,330:0,331:0,365:1,372:350,10:500,12:500})
        b.temperature(0,220)
        b.reset_faults()
        b.start()
        b.wait('normal four-system heating before mirror recheck',
               lambda s:all(v==3 for p in s['outdoor_status'] for v in p),180)
        b.outss.close()
        b.outss = None
        ctx = mp.get_context('spawn')
        values = ctx.Array('i',[-1]*8)
        stop = ctx.Event()
        out = ctx.Queue()
        proc = ctx.Process(target=worker,args=(BOARDS[0],b.outsy,values,stop,out),daemon=True)
        proc.start()
        kind, value = out.get(timeout=30)
        assert kind == 'ready',(kind,value)

        def set_input(ch=None):
            with values.get_lock():
                for index in range(8):values[index] = 0 if index == ch else -1
            event = dict(at=now(),t=time.monotonic(),raw_zero_channel=ch)
            e['input_events'].append(event)
            b.save()
            return event['t']

        def sample(after):
            while True:
                try:kind,s = out.get(timeout=3)
                except queue.Empty:
                    assert proc.is_alive(),'input worker stopped'
                    continue
                if kind == 'error':raise RuntimeError(s)
                if kind != 'sample' or s['t'] < after:continue
                s['read330_at'] = now()
                s['read330_t'] = time.monotonic()
                s['fault_mirrors'] = b.rd(2022,28)
                s['layer_mirror'] = b.rd(2598)[0]
                s['module_comm_fault'] = b.rd(594)[0]
                s['other_outdoor_status'] = b.rd(1625,2)
                e['samples'].append(s)
                return s

        def wait_for(label,after,predicate,seconds,row):
            began = time.monotonic()
            while True:
                s = sample(after)
                if predicate(s):
                    row[label] = s
                    b.save()
                    return s
                assert time.monotonic()-began < seconds,(label,s)

        for cid,ch,alarm,system in [('O-PROTECT-003',3,615,0),
                                    ('O-PROTECT-004',5,617,0),
                                    ('O-PROTECT-005',1,613,0),
                                    ('O-PROTECT-016',0,612,None)]:
            r = dict(id=cid,channel=ch,alarm_parameter=alarm,system=system,status='running')
            e['cases'].append(r)
            wait_for('healthy_both_running',time.monotonic(),
                     lambda s:s['output'][:2]==[1,1] and not any(s['alarms']) and not any(s['fault_mirrors']),220,r)
            applied = set_input(ch)
            offset = alarm-600
            protected = lambda s:(s['output'][:2]==[0,0] if system is None else
                                  s['output'][system]==0 and s['output'][1-system]==1)
            edge = wait_for('protection_first_seen',applied,
                            lambda s:s['alarms'][offset]==1 and protected(s),35,r)
            r['continuous_hold'] = []
            observed = False
            began = time.monotonic()
            while time.monotonic()-began < 55:
                s = sample(applied)
                r['continuous_hold'].append(s)
                if s['alarms'][offset]==1 and s['fault_mirrors'][offset]==1:
                    observed = True
                if observed and time.monotonic()-began>=3:break
            r['mirror_assert_seen'] = observed
            r['source_alarm_dropout_count'] = sum(s['alarms'][offset]!=1 for s in r['continuous_hold'])
            removed = set_input()
            wait_for('automatic_clear',removed,
                     lambda s:s['alarms'][offset]==0 and s['params']['1501']&31==0,35,r)
            wait_for('mirror_clear',removed,lambda s:s['fault_mirrors'][offset]==0,55,r)
            r['status'] = ('保护及镜像软件子范围通过' if observed else
                           '保护动作已见；持续采样下仍未见330报警镜像，保留异常')
            r['finished'] = now()
            b.save()
            print('NTC MIRROR RECHECK',cid,r['status'],'source_dropouts',r['source_alarm_dropout_count'],flush=True)
        e['status'] = 'completed_see_per_case'
    except BaseException:
        e['execution_error'] = traceback.format_exc()
        b.save()
        raise
    finally:
        try:
            b.wr(398,0)
            if proc is not None:
                if values is not None:
                    with values.get_lock():
                        for index in range(8):values[index] = -1
                time.sleep(1)
                stop.set()
                proc.join(10)
                assert not proc.is_alive(),'mirror input worker failed to stop'
                assert proc.exitcode == 0,proc.exitcode
            if b.outss is None:
                b.outss = ConnectHelper.session_with_chosen_probe(
                    unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
                    options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
                b.outss.open()
                b.ot = b.outss.target
            time.sleep(2)
            b.finish()
        finally:
            e['finished'] = now()
            b.save()
            print('EVIDENCE',b.path,flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['mirrors','continuity']+[f'disable{i}' for i in range(6)])
    action=parser.parse_args().action
    if action.startswith('disable'):disable(int(action[-1]))
    else:globals()[action]()


if __name__ == '__main__':main()
