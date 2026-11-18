"""Thirty normal BENCH cycles and a real 2h serial-load observation window.

Only ordinary configuration writes. No time/counter/output forcing. Terminal
measurements and real thermal-load stability remain separate acceptance work.
"""
import json
import os
import time
import traceback
from remaining571_common_20261105 import Bench,now
from run_indoor_bench_20261105 import D,EXPECTED,loads_off


def main():
    previous=json.loads((D/os.environ.get('PSC_BENCH_PREVIOUS_BATCH_JOURNAL','continuation_batches_1976.json')).read_text('utf8'))
    assert previous['batches'] and all(v['exit_code']==0 for v in previous['batches']), 'Inspect previous failed batch before further writes'
    from remaining529_configuration_board_20261105 import main as configuration_cases
    configuration_cases()
    from remaining529_loaded_mode_board_20261105 import main as loaded_mode_cases
    loaded_mode_cases()
    b=Bench('529_cycles_soak')
    try:
        runs=[]
        b.log['cases']['T13-063']={'runs':runs,'passed':False}
        for mode in (2,0,1):
            b.setup(mode)
            b.config({335:1,336:1,337:1,338:1,329:2,330:2,331:1,
                328:30,132:30,135:30,128:2 if mode==1 else 0,412:1,347:100,348:1,349:0,
                315:0,125:0,126:0,334:0,332:0,127:0,333:0,160:250,161:250})
            b.ntc(0,220 if mode==1 else 250)
            for i in range(10):
                entry={'mode':mode,'round':i+1,'start_at':now()}
                runs.append(entry)
                started=time.monotonic()
                entry['running']=b.start()
                assert all(entry['running']['do'][ch] for ch in (3,6,8))
                assert b.rd(2622,18)==EXPECTED
                b.observe('cycle running',1)
                entry['stopped']=b.stop()
                assert loads_off(entry['stopped']) and b.rd(119)[0]==0
                entry['duration_s']=time.monotonic()-started
                entry['passed']=True
                b.save()
                print('NORMAL CYCLE',len(runs),'/30',mode,i+1,round(entry['duration_s'],2),flush=True)
        b.log['cases']['T13-063']['passed']=True
        b.record('T13-063','部分通过','BENCH普通启停30轮已完成：通风/制冷/非热泵制热各10轮，每轮都正常启动、正常关机并核对风机链、负载软件输出清零、[119]为0及三板版本通信。',
            '制冷轮使用零压机需求，非热泵制热轮实际热需求；不覆盖30轮满载压机/全部ACK与实物端子；正式时序另测',b.log['cases']['T13-063'])
        b.setup(1)
        b.config({128:2,125:0,126:0,333:0,334:0,332:0,127:0,329:2,330:2,331:1,
            335:1,336:1,337:1,338:1,412:5,347:5,348:100,349:0,160:250,161:250})
        b.ntc(0,220)
        b.start()
        # Exact required 20min baseline +40min monitor +60min baseline.
        entry={'started':now(),'segments':[],'passed':False,'software_output_only':True,
               'ntc_stimulus':'real ADC + legal calibration; no physical chamber control'}
        b.log['cases']['T13-064']=entry
        trace=D/('soak_samples_'+time.strftime('%H%M%S')+'.ndjson')
        entry['trace_file']=str(trace)
        started=time.monotonic()
        with trace.open('w',encoding='utf8',buffering=1) as tracefile:
            for name,duration,period in (('baseline20min',1200,1),('monitor40min',2400,.15),('baseline60min',3600,1)):
                segment={'name':name,'requested_s':duration,'period_after_response_s':period,
                    'started':now(),'sample_count':0,'timeout_count':0,'observed_AO0_min':1000,'observed_AO0_max':0}
                entry['segments'].append(segment)
                began=time.monotonic()
                heartbeat=began
                while time.monotonic()-began<duration:
                    s=b.snapshot('soak '+name)
                    # Stream the long trace instead of repeatedly copying it into
                    # the main journal, which would distort the polling load.
                    b.log['samples'].pop()
                    segment['sample_count']+=1
                    assert not any(s['faults']) and s['state'][9]==2,s
                    assert s['do'][3]==s['do'][6]==s['do'][8]==1,s
                    assert b.rd(2622,18)==EXPECTED
                    s['total_elapsed_s']=time.monotonic()-started
                    s['segment']=name
                    segment['observed_AO0_min']=min(segment['observed_AO0_min'],s['ao'][0])
                    segment['observed_AO0_max']=max(segment['observed_AO0_max'],s['ao'][0])
                    tracefile.write(json.dumps(s,ensure_ascii=False)+'\n')
                    if time.monotonic()-heartbeat>=30:
                        segment['elapsed_s']=time.monotonic()-began
                        b.save()
                        print('SOAK',name,round(segment['elapsed_s'],1),'total',round(time.monotonic()-started,1),'samples',segment['sample_count'],flush=True)
                        heartbeat=time.monotonic()
                    time.sleep(min(period,max(.001,duration-(time.monotonic()-began))))
                segment['elapsed_s']=time.monotonic()-began
                segment['samples_per_second']=segment['sample_count']/segment['elapsed_s']
                segment['passed']=True
                b.save()
        entry['elapsed_s']=time.monotonic()-started
        assert entry['elapsed_s']>=7200
        entry['passed']=True
        b.record('T13-064','部分通过',f'非热泵制热BENCH实际连续观察{entry["elapsed_s"]:.1f}s：20min基线、40min较高读频、60min基线；所采三板版本/内机故障/风机输出未见异常，逐样本NDJSON已保存。',
            '软件通信和输出观察；无硬件复位原因寄存器/细粒度PID周期独立追踪，实际热工闭环、物理端子和长期老化另测',entry)
        b.stop()
        b.log['passed']=True
    except BaseException:
        b.log['error']=traceback.format_exc()
        b.save()
        raise
    finally:b.finish()
    print('CYCLES AND REAL SOAK COMPLETE',b.path,flush=True)


if __name__=='__main__':main()
