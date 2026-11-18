"""Full wall-clock special sequences using normal protocol on BENCH firmware.

Never shortens the dedicated 150/20/30 second special sequencer waits.
"""
import argparse,time,traceback
from remaining571_common_20261105 import Bench,now
from run_indoor_bench_20261105 import result,loads_off


def main(start=0,limit=6):
    b=Bench('529_special_complete')
    cases=[(3,0,'T13-001'),(3,1,'T13-002'),(4,0,'T13-003'),
           (4,1,'T13-004'),(5,0,'T13-005'),(5,1,'T13-006')][start:start+limit]
    try:
        for mode,after,cid in cases:
            print('SPECIAL START',cid,now(),flush=True)
            b.setup(2);b.config({329:2,330:0,331:1,335:1,336:1,337:1,338:1,
                323:1,324:1,325:after,328:30,132:30,135:30})
            # Establish/stop the prior normal mode through the real sequencer.
            b.start();b.stop()
            entry={'started':now(),'mode':mode,'after_policy':after,'prior_normal':b.rd(326)[0],
                'special_waits_are_real_wall_clock':True,'samples':[],'phase_edges':[]}
            b.log['cases'][cid]=entry;b.wr(236,mode);b.wr(398,1)
            started=time.monotonic();last=None;phases=set();first_special=False;last_print=started
            inconsistent_since=None
            while True:
                s=b.sample(cid);entry['samples'].append(s)
                phase=s['diag'][13];actual_mode=b.rd(236)[0]
                if phase:first_special=True;phases.add(phase)
                edge=(actual_mode,s['state'][9],phase,tuple(s['do']),tuple(s['ao']))
                if edge!=last:
                    entry['phase_edges'].append({'elapsed_s':round(time.monotonic()-started,3),'at':now(),
                        'mode':actual_mode,'sys_step':s['state'][9],'special_step':phase,'do':s['do'],'ao':s['ao']})
                    print('SPECIAL EDGE',cid,round(time.monotonic()-started,1),'mode',actual_mode,'step',phase,'DO',s['do'],flush=True)
                    last=edge;b.save()
                assert not any(s['faults']),(cid,'unrelated fault',s)
                if actual_mode==mode:
                    assert all(s['ao'][i]==0 for i in (0,1,2,9)) and all(s['do'][i]==0 for i in (0,1,2,11,13,14)),(cid,'thermal leakage',s)
                    assert s['count_119']==0,(cid,'compressor running during special mode',s)
                    if phase==1:
                        assert not s['do'][3] and not s['do'][8] and not s['do'][10],(cid,'actuator before damper wait',s)
                    # State/DO/diagnostics occupy separate Modbus reads. A phase
                    # can advance between them. Preserve and re-sample such a
                    # boundary instead of declaring a single torn read a fault.
                    consistent=(phase!=3 or s['do'][10]==1 and s['do'][3]==1 and not s['do'][8]) and (phase!=4 or s['do'][3]==s['do'][8]==1 and s['do'][10]==0)
                    if not consistent:
                        inconsistent_since=inconsistent_since or time.monotonic()
                        entry.setdefault('cross_scan_samples',[]).append(s)
                        assert time.monotonic()-inconsistent_since<1,(cid,'persistent phase/output mismatch',s)
                        b.save();time.sleep(.15);continue
                    inconsistent_since=None
                complete=first_special and ((after==0 and s['state'][9]==0 and phase==0 and loads_off(s)) or
                    (after==1 and actual_mode==entry['prior_normal'] and s['state'][9]==2 and phase==0))
                if complete:entry['completed']=s;break
                assert time.monotonic()-started<850,(cid,'sequence timed out',s)
                if time.monotonic()-last_print>=30:
                    print('SPECIAL WAIT',cid,round(time.monotonic()-started,1),'step',phase,flush=True);last_print=time.monotonic();b.save()
                time.sleep(.4)
            assert 3 in phases if mode==3 else 4 in phases if mode==4 else {3,4,5}.issubset(phases),(cid,phases)
            entry['duration_s']=round(time.monotonic()-started,3);entry['passed']=True;entry['finished']=now()
            result(cid,'部分通过',f'BENCH实等完成：模式{mode}、结束选择{after}，经过阶段{sorted(phases)}，总{entry["duration_s"]}s；专用150/20/30秒未跳过；冷热加湿和压机无误启，结束停机/恢复原正常模式符合。',b.path,
                '逐边沿软件时间戳；实际风阀行程、消毒装置、继电器端子与正式档未测；精确门限另按边沿采样误差核对。',
                '公开模式/时长/结束策略；真实墙钟等待，无计时器或输出RAM写入')
            b.save();b.stop()
            print('SPECIAL PASSED',cid,entry['duration_s'],flush=True)
        b.log['passed']=True
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    print('SPECIAL COMPLETE',b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--start',type=int,default=0);p.add_argument('--limit',type=int,default=6)
    a=p.parse_args();main(a.start,a.limit)
