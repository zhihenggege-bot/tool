"""Repeat loaded cooling/heating -> disinfect without legacy encrypted CSV I/O."""
from remaining_pid_live_20261106 import *


def main():
    b=HeatBench('loaded_modes_to_disinfect')
    try:
        for source,after,cid in ((0,0,'T13-007'),(0,1,'T13-008'),(1,0,'T13-009'),(1,1,'T13-010')):
            b.setup(source)
            b.config({128:1,127:0,332:0,333:0,334:0,129:1,315:0,
                160:150,161:300,125:0,126:0,248:0,320:0,245:1,247:0,
                416:100,417:1,418:0,426:100,427:1,428:0,412:1,
                329:2,330:0,331:1,335:1,336:1,337:1,338:1,
                323:1,324:1,325:after,328:30,132:30,135:30})
            b.temperature(0,220);b.reset_faults();b.start()
            def full(s):return all(v==(2 if source==0 else 3) for pair in s['outdoor_status'] for v in pair)
            before=b.wait(cid+' four compressor feedback',full,170)
            entry=dict(passed=False,source=source,after=after,before=before,
                samples=[],edges=[],timers_modified=False,legacy_csv_access=False,
                da8_precondition='已有手动模式[245]=1、[247]=0；本例不验收冷水阀介质启用逻辑')
            b.log['cases'][cid]=entry;b.save()
            b.c.write_single_register(1,236,3)
            entry['command_at']=now();began=time.monotonic();last=None;last_report=began
            phase_seen=disinfect_seen=False
            while True:
                s=b.snapshot(cid);d=b.rd(872,16);mode=b.rd(236)[0];phase=d[13]
                s.update(t=time.monotonic(),mode=mode,special_phase=phase,
                    disinfect_count=d[14],exhaust_count=d[15])
                entry['samples'].append(s)
                marker=(mode,s['state'][9],phase,tuple(s['do']),tuple(s['ao']),tuple(v for pair in s['outdoor_status'] for v in pair))
                if marker!=last:
                    entry['edges'].append(dict(elapsed_s=time.monotonic()-began,sample=s));last=marker
                    print('LOADED MODE EDGE',cid,round(time.monotonic()-began,2),mode,s['state'][9],phase,s['outdoor_status'],flush=True)
                    b.save()
                if mode==3 and phase in (1,2,3):
                    phase_seen=True
                    assert all(v not in (2,3,4) for pair in s['outdoor_status'] for v in pair),s
                    assert all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
                    disinfect_seen|=bool(s['do'][10])
                assert not any(s['faults']),s
                complete=phase_seen and disinfect_seen and (
                    after==0 and phase==0 and s['state'][9]==0 and loads_off(s) or
                    after==1 and mode==source and phase==0 and s['state'][9]==2)
                if complete:entry['complete']=s;break
                assert time.monotonic()-began<900,(cid,'mode transition timeout',s)
                if time.monotonic()-last_report>=30:
                    print('LOADED MODE WAIT',cid,round(time.monotonic()-began,1),mode,phase,flush=True)
                    b.save();last_report=time.monotonic()
                time.sleep(.3)
            if after:entry['restored_full_load']=b.wait(cid+' restored four compressor feedback',full,170)
            entry.update(passed=True,duration_s=time.monotonic()-began)
            b.record_local(cid,True,
                f'当前V10.53/V12.39测试版，模式{source}四压机运行反馈先建立，正常切到消毒；旧模式退出后才进入消毒，实际消毒阶段完整运行1min；结束选择{after}符合'+
                ('，原模式恢复并再次取得四压机运行反馈。' if after else '，最后步骤0且负载软件输出清零。')+
                '只读软件状态，不替代物理端子或实际消毒效果；不访问旧加密CSV，旧异常保留。',entry)
            b.stop()
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish()
        print('LOADED MODES RESTORED',b.log.get('restored'),b.path,flush=True)


if __name__=='__main__':main()
