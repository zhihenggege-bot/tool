"""Actual 600/1200 second mode-switch hold, without timer acceleration/pokes."""
from remaining_pid_live_20261106 import *


def main(qhs):
    assert qhs in (600,1200)
    cid='T11-104' if qhs==600 else 'T11-105'
    b=HeatBench('auto_long_qhs_'+str(qhs))
    ss=None
    try:
        b.setup(1)
        b.config({128:0,127:0,332:0,333:0,334:1,125:0,126:1,248:1,
            168:0,160:250,161:250,162:500,120:20,361:200,412:1,
            320:0,321:50,322:qhs,315:0,346:0,329:2,330:0,331:0})
        b.temperature(0,250)
        ai_exact(b,601)
        ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target;sy=b.sy
        def sample(label):
            s=b.snapshot(label);d=b.rd(872,22)
            s.update(t=time.monotonic(),mode=b.rd(236)[0],humidity=b.rd(501)[0],
                switch_count=d[12],switch_direction=d[11],humidity_demand=d[20],
                active=t.read8(sy['IndoorActiveWorkMode'][0]),
                pending=struct.unpack('<i',struct.pack('<I',t.read32(sy['IndoorPendingWorkMode'][0])))[0])
            return s
        b.start()
        # Enable after the start observer returns, so its settling wait cannot
        # hide the first few qualification counts from this long-run journal.
        b.config({320:1})
        entry=dict(passed=False,qhs=qhs,edges=[],timers_modified=False)
        b.log['cases'][cid]=entry
        began=time.monotonic();last=None;marks={}
        while True:
            s=sample(cid)
            assert not any(s['faults']) and s['humidity']==601 and s['humidity_demand']==0,s
            if s['switch_count']!=last or s['pending']!=-1:
                entry['edges'].append(s);marks.setdefault(s['switch_count'],s['t']);last=s['switch_count']
                if last%30==0 or s['pending']!=-1:
                    b.save();print('LONG QHS',qhs,'count',last,'elapsed',round(time.monotonic()-began,2),flush=True)
            # Keep only distinct count observations. snapshot already appended
            # every sample; release redundant copies to bound long-run journals.
            b.log['samples']=b.log['samples'][-3:]
            if s['pending']==0 or s['mode']==0:break
            assert s['mode']==1 and s['pending']==-1 and s['switch_count']<qhs,s
            assert time.monotonic()-began<qhs+3
            time.sleep(.12)
        assert all(n in marks for n in range(1,qhs)), ('missing counter edges',set(range(1,qhs))-marks.keys())
        elapsed=s['t']-marks[2]
        assert qhs-2-.5<=elapsed<=qhs-2+.5,elapsed
        entry.update(trigger=s,count2_to_trigger_s=elapsed)
        transition=[];began=time.monotonic();last_transition=None
        while True:
            s=sample('long_QHS_transition');transition.append(s)
            assert not any(s['ao'][i] for i in (0,1,2,9)),s
            marker=(s['active'],s['mode'],s['pending'],s['state'][9])
            if marker!=last_transition:
                print('LONG QHS TRANSITION',qhs,round(time.monotonic()-began,2),marker,flush=True)
                last_transition=marker
            if s['active']==0 and s['mode']==0 and s['pending']==-1 and s['state'][9]==2:break
            assert time.monotonic()-began<150,s
            time.sleep(.2)
        entry.update(passed=True,transition=transition,completed=now())
        b.record_local(cid,True,f'QHS={qhs}秒真实连续计时，1至{qhs-1}逐计数完整；计数2首次观察到触发{elapsed:.3f}s；旧制热退出、新制冷正常运行均回读。不改计时器；AI1工程映射为60.1%RH，未做物理湿度信号/端子验收。',entry)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        if ss:ss.close()
        b.finish()
        print('LONG QHS RESTORED',qhs,b.log.get('restored'),b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('qhs',type=int);main(p.parse_args().qhs)
