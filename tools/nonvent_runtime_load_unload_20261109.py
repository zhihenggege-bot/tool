"""Real load/unload feedback with received runtime and raw temperature INPUTs.

Never changes a demand, command, feedback, persistent counter, or timer.
"""
from nonvent_runtime_selection_inputs_20261109 import RuntimeReports
from nonvent_ntc_input_boundaries_20261109 import *
from nonvent_supplement_v1055_20261109 import restored_latest
import subprocess, sys


def run():
    b=CheckedBench('runtime_real_load_unload_inputs');ntc=None;reports=None
    try:
        ntc=RawNtcInput(b);reports=RuntimeReports(b,input_fixture=ntc)
        def configure():
            b.setup(0)
            b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
                160:250,161:250,315:1,327:1,316:350,317:220,318:0,319:120,
                320:0,346:0,245:1,247:0,329:2,330:0,331:0,365:1,
                411:200,10:500,12:500,493:0})
            b.temperature(0,250);b.reset_faults()
        def sample(label):
            s=b.snapshot(label)
            s.update(target=b.rd(881)[0],actual=b.rd(119)[0],fresh=signed16(b.rd(512)[0]))
            s['active']=[(m+1,c+1) for m,pair in enumerate(s['outdoor_status']) for c,v in enumerate(pair) if v==2]
            assert not any(s['faults']),s
            return s
        def hold(entry,expected,target,label):
            began=time.monotonic();stable=None;heartbeat=began
            while True:
                paused();s=sample(label);entry['samples'].append(s)
                # 119 is refreshed asynchronously by multiple legacy paths.
                # Ordering uses individual real circuit feedback; retain 119
                # for diagnosis without inventing a display-coherence test.
                if s['active']==expected and s['target']==target:
                    if stable is None:stable=time.monotonic()
                    if time.monotonic()-stable>=4:return s
                else:stable=None
                if time.monotonic()-heartbeat>=20:
                    print('RUNTIME LOAD/UNLOAD',label,round(time.monotonic()-began,1),s['active'],s['target'],flush=True)
                    b.save();heartbeat=time.monotonic()
                assert time.monotonic()-began<220,('expected genuine feedback unavailable',label,s)
                time.sleep(.15)
        for short,cid in ((0,'T10-010'),(1,'T10-011')):
            configure();reports.set(1,19000,short);ntc.set(2,230)
            b.wait('raw23C target1 input',lambda s:signed16(b.rd(512)[0])==230,10)
            e=dict(passed=False,short_compressor=short+1,samples=[],scope='Received cumulative runtime INPUT simulation; real control/316 feedback; not real cumulative duration measurement')
            b.log['cases'][cid]=e;b.save();b.wr(398,1)
            first=hold(e,[(1,short+1)],1,'short compressor starts first')
            ntc.set(2,260);both=hold(e,[(1,1),(1,2)],2,'same running unit fills before stopped unit')
            ntc.set(2,230);last=hold(e,[(1,short+1)],1,'long compressor stops first')
            e.update(passed=True,first=first,both=both,last=last)
            b.record_local(cid,True,f'V10.55接收累计输入外机1较短19000s，同机压机{short+1}较短；NTC2原始ADC输入23→26→23℃，正常公式目标1→2→1，真实316反馈依次为外机1短压机、同外机两台、仅短压机，各稳定4s。验证短先启、长先停及已运行外机优先补满；未改需求/命令/反馈/计时或316累计。非物理动力/端子及正式时序验收。',e)
            b.stop()
        for longest,cid in ((1,'T10-012'),(2,'T10-013')):
            configure();reports.set(3-longest,19000,0);ntc.set(2,340)
            b.wait('raw34C target4 input',lambda s:signed16(b.rd(512)[0])==340,10)
            e=dict(passed=False,longest_unit=longest,samples=[],scope='Received runtime INPUT simulation; real normal unload and 316 feedback')
            b.log['cases'][cid]=e;b.save();b.wr(398,1)
            before=hold(e,[(1,1),(1,2),(2,1),(2,2)],4,'four actual compressors before unload')
            ntc.set(2,310);expected=[(m,c) for m in (1,2) for c in (1,2) if (m,c)!=(longest,2)]
            began=time.monotonic();first_off=None
            while first_off is None:
                paused();s=sample('first falling feedback');e['samples'].append(s)
                if len(s['active'])<4:
                    assert s['active']==expected,('wrong first unload',longest,s)
                    first_off=s
                assert time.monotonic()-began<180,s
                time.sleep(.15)
            after=hold(e,expected,3,'longest unit and longest compressor unloaded')
            e.update(passed=True,before=before,first_off=first_off,after=after)
            b.record_local(cid,True,f'V10.55接收累计输入外机{longest}较长19000s，两机压机2均较长；NTC2原始ADC输入34→31℃，正常公式目标4→3。四台真实制冷反馈建立后，首次消失反馈正是外机{longest}/压机2，其余三台保持运行并稳定4s。未改需求/命令/反馈/计时或316累计。非物理动力/端子及正式时序验收。',e)
            b.stop()
        data=json.loads(RESULTS.read_text('utf8'))
        for cid in ('T10-010','T10-011','T10-012','T10-013'):
            data[cid]['inputs']='Received runtime fields and NTC2 raw ADC/filter INPUT simulation only; real commands/feedback, no persistent-counter or timer forcing'
        dump(RESULTS,data)
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.stop()
            if reports:reports.close()
            if ntc:ntc.close()
            time.sleep(12)
        finally:b.finish()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    path=D/('runtime_load_unload_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),status='waiting_without_hardware',dependency=str(a.after),ventilation='Deferred by user');dump(path,q)
    try:
        while True:
            paused();prior=json.loads(a.after.read_text('utf8'))
            if prior.get('finished'):break
            time.sleep(3)
        assert prior.get('status')=='completed',prior
        restored_latest();q['status']='running';dump(path,q);run();restored_latest();q['checks']=[]
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8')
            q['checks'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(path,q);assert proc.returncode==0
        q['status']='completed'
    except BaseException:q.update(status='stopped_on_error',error=traceback.format_exc());raise
    finally:q['finished']=now();dump(path,q)
