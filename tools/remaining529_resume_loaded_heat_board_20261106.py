"""Resume only interrupted BENCH full-load heat -> disinfect cases."""
import json,time,traceback
import csv
from pathlib import Path
from remaining571_common_20261105 import Bench,now
from run_indoor_bench_20261105 import D,R,RESULTS,loads_off,dump

CASES=('T13-010',)

def record_result(cid,status,actual,evidence,limitations):
    data=json.loads(RESULTS.read_text('utf8')) if RESULTS.exists() else {}
    previous=data.get(cid,{})
    history=list(previous.get('history',[]))
    if previous:
        history.append({k:v for k,v in previous.items() if k!='history'})
    data[cid]={'status':status,'actual':actual,
        'evidence':str(evidence.relative_to(R)).replace('\\','/'),
        'restored':limitations,'inputs':'330/316 BENCH软件状态；压机动力隔离；不是物理端子测量',
        'at':now(),'history':history}
    dump(RESULTS,data)
    sidecar=R/'remaining529续测记录_20261106.csv'
    rows=[]
    if sidecar.exists():
        with sidecar.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    rows.append({'用例编号':cid,'结论':status,'实际结果':actual,'证据':data[cid]['evidence'],
        '时间':data[cid]['at'],'恢复及限制':limitations})
    with sidecar.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('RECORDED SIDECAR',cid,status,flush=True)

def main():
    b=Bench('529_resume_loaded_heat')
    try:
        for cid in CASES:
            after=0 if cid=='T13-009' else 1
            try:
                b.setup(1)
                b.config({128:1,127:0,332:0,129:1,315:0,160:150,161:300,125:0,126:0,
                    416:100,417:1,418:0,426:100,427:1,428:0,412:1,
                    329:2,330:0,331:1,335:1,336:1,337:1,338:1,
                    323:1,324:1,325:after,328:30,132:30,135:30})
                b.ntc(0,220);b.reset_faults();b.start()
                running=b.wait(cid+' all four heating compressor feedback',
                    lambda s:all(x==3 for pair in s['outdoor_status'] for x in pair),170)
                entry={'source':1,'after':after,'before':running,'started':now(),
                    'special_edges':[],'samples':[],'transient_read_errors':[]}
                b.log['cases'][cid]=entry;b.save()
                b.c.write_single_register(1,236,3);entry['mode_command_at']=now()
                began=time.monotonic();last=None;phase_seen=False;disinfect_seen=False;last_report=began
                while True:
                    try:s=b.sample(cid+' full heat -> disinfect')
                    except Exception as exc:
                        entry['transient_read_errors'].append({'at':now(),'error':repr(exc)})
                        b.save();time.sleep(.5)
                        assert time.monotonic()-began<900,(cid,'serial read timeout during transition',repr(exc))
                        continue
                    entry['samples'].append(s);actual=b.rd(236)[0];phase=s['diag'][13]
                    key=(actual,s['state'][9],phase,tuple(s['do']),tuple(s['ao']))
                    if key!=last:
                        edge={'elapsed_s':time.monotonic()-began,'mode':actual,'step':s['state'][9],
                            'special_step':phase,'do':s['do'],'ao':s['ao'],'outdoor_status':s['outdoor_status']}
                        entry['special_edges'].append(edge);last=key;b.save()
                        print('EDGE',cid,round(edge['elapsed_s'],2),actual,s['state'][9],phase,flush=True)
                    if actual==3 and phase in (1,2,3):
                        phase_seen=True
                        assert all(x not in (2,3,4) for pair in s['outdoor_status'] for x in pair),s
                        assert all(s['ao'][i]==0 for i in (0,1,2,9)),s
                        if s['do'][10]:disinfect_seen=True
                    assert not any(s['faults']),s
                    complete=phase_seen and disinfect_seen and (
                        after==0 and phase==0 and s['state'][9]==0 and loads_off(s) or
                        after==1 and actual==1 and phase==0 and s['state'][9]==2)
                    if complete:entry['complete']=s;break
                    assert time.monotonic()-began<900,(cid,'transition timeout',s)
                    if time.monotonic()-last_report>=30:
                        print('WAIT',cid,round(time.monotonic()-began,1),actual,phase,flush=True)
                        b.save();last_report=time.monotonic()
                    time.sleep(.4)
                if after:
                    entry['restored_full_load']=b.wait(cid+' restored four heating compressor feedback',
                        lambda s:all(x==3 for pair in s['outdoor_status'] for x in pair),170)
                entry['duration_s']=time.monotonic()-began;entry['passed']=True
                record_result(cid,'部分通过',
                    f'制热模式四压机运行反馈实际建立，正常切换后退出热泵并完成消毒1min；结束选择{after}符合'+
                    ('，原制热模式恢复后再次取得四压机反馈。' if after else '，最终停机且所有负载软件输出为0。'),
                    b.path,'330/316 BENCH软件状态及实时时序；压机动力隔离；物理加热/消毒与正式秒数另验')
            except Exception as exc:
                entry=b.log['cases'].setdefault(cid,{})
                entry['error']=traceback.format_exc();b.save()
                record_result(cid,'环境受限' if 'No response' in str(exc) or '应答长度不足' in str(exc) else '失败',
                    str(exc)[-1000:],b.path,'原始失败保留；检查并恢复后再重测；未改固件')
            b.stop()
    finally:
        b.finish()
    print('HEATING M3 RESUME COMPLETE',b.path,flush=True)

if __name__=='__main__':main()
