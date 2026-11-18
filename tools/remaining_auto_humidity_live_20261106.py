"""Real 60-second auto-switch, strict RH boundary and interrupted hold."""
from remaining_pid_live_20261106 import *


def main():
    b = HeatBench('auto_humidity_continuity')
    session = None
    try:
        b.setup(1)
        b.config({128: 0, 127: 0, 332: 0, 333: 0, 334: 1, 125: 1, 126: 1, 248: 1,
                  168: 0, 160: 250, 161: 250, 162: 500, 120: 20, 361: 200,
                  412: 1, 320: 0, 321: 50, 322: 60, 315: 0, 346: 0,
                  329: 2, 330: 0, 331: 0})
        b.temperature(0, 250)
        ai_exact(b, 601)
        session = ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1], target_override=BOARDS[2][2],
            options={'connect_mode': 'attach', 'resume_on_disconnect': True, 'frequency': 1000000})
        session.open()
        t = session.target
        sy = b.sy
        def sample(label):
            s = b.snapshot(label)
            d = b.rd(872, 22)
            s.update(t=time.monotonic(), mode=b.rd(236)[0], humidity=b.rd(501)[0],
                     switch_direction=d[11], switch_count=d[12], reason=d[21],
                     heat_demand=d[18], humidity_demand=d[20],
                     active=t.read8(sy['IndoorActiveWorkMode'][0]),
                     pending=struct.unpack('<i', struct.pack('<I', t.read32(sy['IndoorPendingWorkMode'][0])))[0])
            return s
        def hold(label, seconds, predicate):
            rows = []
            began = time.monotonic()
            last = None
            while time.monotonic()-began < seconds:
                s = sample(label)
                rows.append(s)
                assert predicate(s), (label, s)
                marker = (s['mode'], s['switch_count'], s['pending'], s['state'][9])
                if marker != last:
                    print('AUTO HOLD', label, round(time.monotonic()-began, 2), marker, flush=True)
                    last = marker
                time.sleep(.1)
            b.log.setdefault('auto_phases', {})[label] = rows
            b.save()
            return rows
        b.start()
        disabled = hold('disabled_65s', 65, lambda s:s['mode']==1 and s['pending']==-1 and s['switch_count']==0)
        b.config({320: 1})
        ai_exact(b, 600)
        boundary = hold('exact_RH60_65s', 65, lambda s:s['mode']==1 and s['pending']==-1 and s['switch_count']==0 and s['humidity']==600)
        ai_exact(b, 601)
        interrupted = []
        b.log.setdefault('auto_phases', {})['qualify_to_58'] = interrupted
        began = time.monotonic()
        last_count = None
        while True:
            s = sample('qualify_to_58')
            interrupted.append(s)
            if s['switch_count']!=last_count and s['switch_count']%10==0:
                print('AUTO INTERRUPT COUNT',s['switch_count'],flush=True)
                b.save()
            last_count=s['switch_count']
            assert s['mode']==1 and s['pending']==-1 and s['humidity']==601, s
            if s['switch_count']==58: break
            assert time.monotonic()-began < 62
            time.sleep(.08)
        b.log.setdefault('auto_phases', {})['qualify_to_58'] = interrupted
        ai_exact(b, 600)
        cancel_started=time.monotonic()
        cancellation=[]
        while True:
            s=sample('cancel_input_accepted_wait_scan')
            cancellation.append(s)
            assert s['mode']==1 and s['pending']==-1 and s['humidity']==600, s
            if s['switch_count']==0: break
            assert time.monotonic()-cancel_started<2, s
            time.sleep(.05)
        b.log['auto_phases']['cancel_input_accepted_wait_scan']=cancellation
        reset = hold('cancel_at_58_reset', 3, lambda s:s['mode']==1 and s['pending']==-1 and s['switch_count']==0)
        ai_exact(b, 601)
        complete = []
        b.log['auto_phases']['complete_QHS60'] = complete
        began = time.monotonic()
        last_count = None
        while True:
            s = sample('complete_QHS60')
            complete.append(s)
            if s['switch_count']!=last_count and s['switch_count']%10==0:
                print('AUTO COMPLETE COUNT',s['switch_count'],flush=True)
                b.save()
            last_count=s['switch_count']
            if s['pending']==0 or s['mode']==0: break
            assert s['pending']==-1 and s['mode']==1 and s['humidity']==601, s
            assert time.monotonic()-began < 63
            time.sleep(.08)
        assert any(s['switch_count']==59 for s in complete)
        event = complete[-1]
        count1 = next(s for s in complete if s['switch_count']==1)
        elapsed_from_count1 = event['t']-count1['t']
        # ai_exact returns only after the engineering input has settled. The
        # first observed count=1 may therefore already be late in that second.
        # Verify every count, then time a later complete observed interval.
        marks={}
        for row in complete: marks.setdefault(row['switch_count'],row['t'])
        assert all(n in marks for n in range(1,60)), marks
        elapsed_from_count2=event['t']-marks[2]
        assert 57.6 <= elapsed_from_count2 <= 58.4, elapsed_from_count2
        assert .6 <= event['t']-marks[59] <= 1.4
        b.log['auto_phases']['complete_QHS60'] = complete
        b.log['switch_trigger'] = event
        b.log['count1_to_trigger_s'] = elapsed_from_count1
        b.log['count2_to_trigger_s'] = elapsed_from_count2
        transition = []
        began = time.monotonic()
        while True:
            s = sample('normal_heat_to_cool_transition')
            transition.append(s)
            assert not any(s['ao'][i] for i in (0, 1, 9)), s
            assert not any(s['do'][i] for i in (0, 1, 2, 13, 14, 15)), s
            if s['active']==0 and s['mode']==0 and s['pending']==-1 and s['state'][9]==2: break
            assert time.monotonic()-began < 150
            time.sleep(.15)
        b.log['auto_phases']['normal_heat_to_cool_transition'] = transition
        b.log['completed_transition'] = transition[-1]
        b.save()
        entry = {'passed': True, 'phases': b.log['auto_phases'], 'count1_to_trigger_s': elapsed_from_count1,
                 'trigger': event, 'new_cool_running': transition[-1]}
        for cid, text in (
            ('T11-094', f'控湿制热RH60.1%、加湿为0，连续QHS60触发转冷；58秒撤销后计数清0，重新连续计时；1至59逐计数完整，计数2首次观察到触发{elapsed_from_count2:.3f}s；旧模式退出到新制冷运行全过程已回读。'),
            ('T11-097', 'RH60.0%精确等号保持65s不切换；60.1%满足；撤销后重计及转冷全过程符合。'),
            ('T11-101', '自动切换禁用且高湿条件满足65s不切换；启用后完成严格边界、撤销重计和自动转冷。手动模式变更未在本例补测。')):
            b.record_local(cid, True, text+'AI1为工程映射软件模拟；未缩短QHS计数。', entry)
    except Exception:
        b.log['error'] = traceback.format_exc()
        b.save()
        raise
    finally:
        if session: session.close()
        b.finish()
        print('AUTO HUMIDITY RESTORED', b.log.get('restored'), b.path, flush=True)


if __name__ == '__main__': main()
