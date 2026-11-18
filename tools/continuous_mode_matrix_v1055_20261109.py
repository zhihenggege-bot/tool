"""All thirty ordered mode handoffs with ordinary commands and no thermal load.

The separately journalled four full-load-to-disinfect cases qualify loaded
handoffs; this matrix only covers the stated no-thermal-load combinations.
"""
from v1055_bench_context_20261109 import *
from remaining_pid_live_20261106 import *


def main():
    b=HeatBench('continuous_thirty_mode_transitions_v1055')
    b.log['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ss=None
    try:
        ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target
        def sample(label):
            s=b.snapshot(label)
            s.update(t=time.monotonic(),mode=b.rd(236)[0],special_phase=b.rd(885)[0],
                active=t.read8(b.sy['IndoorActiveWorkMode'][0]),
                pending=struct.unpack('<i',struct.pack('<I',t.read32(b.sy['IndoorPendingWorkMode'][0])))[0])
            return s
        def ready(s,mode):
            actuators=(s['do'][3] and s['do'][10] and not s['do'][8]) if mode in (3,5) else (s['do'][3] and s['do'][8] and not s['do'][10])
            return s['mode']==mode and s['active']==mode and s['pending']==-1 and s['state'][9]==2 and actuators
        pairs=[(s,v) for s in range(6) for v in range(6) if s!=v]
        ids={pair:f'T13-{11+i:03d}' for i,pair in enumerate(pairs)}
        # An Eulerian route covers each ordered handoff once. Each completed
        # target is the established source of the next case; the firmware's
        # handoff performs all required shutdown/startup waits normally.
        unused={s:[v for v in range(6) if s!=v] for s in range(6)}
        stack=[0];route=[]
        while stack:
            if unused[stack[-1]]:stack.append(unused[stack[-1]].pop())
            else:route.append(stack.pop())
        route.reverse();ordered=list(zip(route,route[1:]))
        assert len(ordered)==30 and set(ordered)==set(pairs)
        b.log['handoff_route']=ordered
        b.setup(0)
        b.config({128:0,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:320,161:150,315:0,320:0,346:0,245:1,247:0,
            329:2,330:0,331:1,335:1,336:1,337:1,338:1,
            323:5,324:5,325:0,328:30,132:30,135:30})
        b.temperature(0,250);b.reset_faults();b.start()
        began=time.monotonic()
        while not ready(sample('initial source actuators established'),0):
            assert time.monotonic()-began<60, 'initial normal-mode actuators not established'
            time.sleep(.2)
        for source,target in ordered:
                cid=ids[source,target]
                initial=sample(cid+' source ready');assert ready(initial,source),initial
                assert b.rd(2622,18)==runtime.EXPECTED
                entry=dict(passed=False,source=source,target=target,before=initial,
                    samples=[],edges=[],scope='无冷热湿负载模式迁移；四压机满载迁移另见T13-007至010',
                    da8_precondition='遗留冷水阀设为已有手动模式[245]=1、[247]=0；不据此验收T06-024/025介质启用问题')
                b.log['cases'][cid]=entry;b.save()
                b.c.write_single_register(1,236,target)
                began=time.monotonic();last=None;last_report=began
                while True:
                    s=sample(cid+' handoff');entry['samples'].append(s)
                    assert not any(s['faults']),s
                    assert all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
                    assert all(v not in (2,3,4) for pair in s['outdoor_status'] for v in pair),s
                    marker=(s['mode'],s['active'],s['pending'],s['state'][9],s['special_phase'],tuple(s['do']),tuple(s['ao']))
                    if marker!=last:
                        entry['edges'].append(dict(elapsed_s=time.monotonic()-began,sample=s));last=marker
                        b.save();print('MODE HANDOFF',cid,source,target,round(time.monotonic()-began,2),marker[:5],flush=True)
                    if ready(s,target):
                        assert b.rd(2622,18)==runtime.EXPECTED
                        entry['complete']=s;break
                    assert time.monotonic()-began<400,(cid,'handoff timeout',s)
                    if time.monotonic()-last_report>=30:
                        print('MODE HANDOFF WAIT',cid,round(time.monotonic()-began,1),marker[:5],flush=True)
                        b.save();last_report=time.monotonic()
                    time.sleep(.2)
                entry.update(passed=True,duration_s=time.monotonic()-began)
                b.record_local(cid,True,f'正常模式指令{source}→{target}；源模式执行器先建立，记录活动模式、待切模式、主步骤及消排毒步骤，最终目标模式执行器正常建立；全过程无冷热湿输出及压机运行反馈。'
                    '此例为无冷热湿负载迁移，软件回读；不替代满载、物理输出、正式档或消排毒完整时长验收。',entry)
        assert len(b.log['cases'])==30 and all(v['passed'] for v in b.log['cases'].values())
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        if ss:ss.close()
        b.finish()
        print('MODE HANDOFFS RESTORED',b.log.get('restored'),b.path,flush=True)


if __name__=='__main__':main()
