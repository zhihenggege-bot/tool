"""Full-load ordinary mode -> disinfect -> stop/restore, normal HMI commands."""
import time
from remaining571_common_20261105 import Bench,case_error,now
from run_indoor_bench_20261105 import loads_off

def main():
    b=Bench('529_loaded_mode')
    try:
        for source,after,cid in ((0,0,'T13-007'),(0,1,'T13-008'),(1,0,'T13-009'),(1,1,'T13-010')):
            try:
                b.setup(source)
                b.config({128:1,127:0,332:0,129:1,315:0,160:150,161:300,125:0,126:0,
                    416:100,417:1,418:0,426:100,427:1,428:0,412:1,
                    329:2,330:0,331:1,335:1,336:1,337:1,338:1,
                    323:1,324:1,325:after,328:30,132:30,135:30})
                b.ntc(0,220)
                b.reset_faults()
                b.start()
                running=b.wait(cid+' full load',lambda s:all(x==(2 if source==0 else 3)
                    for pair in s['outdoor_status'] for x in pair),170)
                entry={'source':source,'after':after,'before':running,'started':now(),
                    'special_edges':[],'samples':[]}
                b.log['cases'][cid]=entry
                # The transition deliberately echoes the source mode until its
                # shutdown is complete, so do not demand immediate 236=3.
                b.c.write_single_register(1,236,3)
                entry['mode_command_at']=now()
                began=time.monotonic()
                phase_seen=False
                disinfect_seen=False
                last=None
                last_report=began
                while True:
                    s=b.sample(cid+' full-load mode transition')
                    entry['samples'].append(s)
                    actual=b.rd(236)[0]
                    phase=s['diag'][13]
                    key=(actual,s['state'][9],phase,tuple(s['do']),tuple(s['ao']))
                    if key!=last:
                        edge={'elapsed_s':time.monotonic()-began,'mode':actual,'step':s['state'][9],
                            'special_step':phase,'do':s['do'],'ao':s['ao'],'outdoor_status':s['outdoor_status']}
                        entry['special_edges'].append(edge)
                        print('M3 EDGE',cid,round(edge['elapsed_s'],2),actual,s['state'][9],phase,flush=True)
                        last=key
                        b.save()
                    if actual==3 and phase in (1,2,3):
                        phase_seen=True
                        assert all(x not in (2,3,4) for pair in s['outdoor_status'] for x in pair),s
                        assert all(s['ao'][i]==0 for i in (0,1,2,9)),s
                        if s['do'][10]:disinfect_seen=True
                    assert not any(s['faults']),s
                    complete=phase_seen and disinfect_seen and (
                        after==0 and phase==0 and s['state'][9]==0 and loads_off(s) or
                        after==1 and actual==source and phase==0 and s['state'][9]==2)
                    if complete:
                        entry['complete']=s
                        break
                    assert time.monotonic()-began<900,(cid,'timeout',s)
                    if time.monotonic()-last_report>30:
                        print('M3 WAIT',cid,round(time.monotonic()-began,1),actual,phase,flush=True)
                        b.save()
                        last_report=time.monotonic()
                    time.sleep(.4)
                if after:
                    entry['restored_full_load']=b.wait(cid+' restored actual full load',lambda s:
                        all(x==(2 if source==0 else 3) for pair in s['outdoor_status'] for x in pair),170)
                entry['duration_s']=time.monotonic()-began
                entry['passed']=True
                b.record(cid,'部分通过',f'正常模式{source}四压机运行反馈已建立，正常改模式进入消毒；旧模式先退出，消毒实际建立并完成1min；结束选择{after}符合'+
                    ('，原模式恢复后四压机反馈再次建立。' if after else '，最终步骤0且负载软件输出清零。'),
                    '控制板/软件状态和实时时序；隔离模拟负载，物理端子、实际消毒及正式档另验',entry)
            except Exception as e:case_error(b,cid,e)
            b.stop()
        b.log['passed']=not any('error' in v for v in b.log['cases'].values())
    finally:b.finish()
    print('LOADED MODE COMPLETE',b.path,flush=True)

if __name__=='__main__':main()
