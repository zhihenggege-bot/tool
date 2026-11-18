"""Automatic mode gates: exact reheat ratio and genuine compressor feedback.

The accepted winter minimum supplies exact normal heat demand at neutral room
temperature. This tests switching gates, not PID generation of 500/501 demand.
"""
from nonvent_ntc_input_boundaries_20261109 import *
from nonvent_eev_pair_live_20261109 import PairedBench
from nonvent_supplement_v1055_20261109 import restored_latest
from nonvent_coil_input_diagnostic_20261109 import DiagnosticInput
from remaining_pid_live_20261106 import ai_exact
import subprocess,sys


def run(counts_only=False):
    b=PairedBench('auto_exact_reheat_inputs');fixture=None
    try:
        fixture=DiagnosticInput(b)
        def setup(control):
            b.setup(0);b.config({128:0,127:1,129:1,332:1,333:0,334:0,
                125:control,126:control,248:control,160:250,161:250,162:500,
                120:20,361:200,412:1,416:100,417:1,418:0,
                347:1,348:1000,349:0,315:0,320:0,321:50,322:60,346:500,
                245:1,247:0,329:2,330:0,331:0,495:0,493:0})
            # Neutral cooling PID has Z=0 and correctly preserves zero actual
            # compressors. Establish reheat's one-compressor floor with a
            # genuine negative cooling error before moving into neutral.
            fixture.set(0,240);fixture.set(2,-10)
            if control:ai_exact(b,500)
            b.wait('negative cooling error and negative fresh raw inputs',lambda s:signed16(b.rd(511)[0])==240 and signed16(b.rd(512)[0])==-10,10)
            b.reset_faults();b.start()
            b.wait('genuine reheat one-compressor floor established',
                lambda s:sum(v==2 for pair in s['outdoor_status'] for v in pair)==1,180)
            fixture.set(0,250)
            b.wait('neutral room after actual compressor established',lambda s:signed16(b.rd(511)[0])==250,10)
            b.config({332:0});time.sleep(.3);b.config({332:1})
        def sample(label):
            s=b.snapshot(label);s.update(mode=b.rd(236)[0],demand=b.rd(890)[0],
                switch=b.rd(883,2),actual=b.rd(119)[0],room=signed16(b.rd(511)[0]))
            s['running']=sum(v==2 for pair in s['outdoor_status'] for v in pair)
            s['mode_after_snapshot']=b.rd(236)[0]
            with fixture.io:
                pending=fixture.t.read32(b.sy['IndoorPendingWorkMode'][0])
                s['pending']=pending if pending<0x80000000 else pending-0x100000000
                s['active_mode']=fixture.t.read8(b.sy['IndoorActiveWorkMode'][0])
            if s['mode_after_snapshot']!=s['mode']:
                s['crossed_mode_transition']=True;s['mode']=s['mode_after_snapshot']
            assert not any(s['faults']),s
            return s
        def establish(n,demand,entry,label):
            began=time.monotonic();stable=None
            while True:
                paused();s=sample(label);entry['samples'].append(s)
                if s['mode']==0 and s['running']==n and s['demand']==s['ao'][0]==demand:
                    if stable is None:stable=time.monotonic()
                    if time.monotonic()-stable>=3:return s
                else:stable=None
                assert time.monotonic()-began<200,('switch gate precondition unavailable',label,s)
                time.sleep(.15)
        def veto(seconds,n,demand,entry,label):
            began=time.monotonic();heartbeat=began
            while time.monotonic()-began<seconds:
                paused();s=sample(label);entry['samples'].append(s)
                thermal_ok=(s['demand']>=demand and s['ao'][0]>=demand) if n==2 else s['demand']==s['ao'][0]==demand
                assert s['mode']==0 and s['running']==n and thermal_ok and s['switch']==[0,0],s
                if time.monotonic()-heartbeat>=20:
                    print('AUTO GATE VETO',label,round(time.monotonic()-began,1),flush=True);heartbeat=time.monotonic();b.save()
                time.sleep(.15)
        def qualify(entry,label):
            began=time.monotonic();marks={};heartbeat=began
            while True:
                paused();s=sample(label);entry['samples'].append(s)
                if s['mode']==1 or s['pending']==1:break
                if s['demand']!=501 and 59 in marks and s['switch']==[0,0]:
                    # Snapshot spans separate Modbus transactions. At QHS60
                    # normal mode migration can clear heat before the earlier
                    # mode word reflects the new mode. Preserve that sample,
                    # and require the actual mode change within one second.
                    entry.setdefault('transition_crossing_samples',[]).append(s)
                    transition_began=time.monotonic()
                    while s['mode']!=1 and s['pending']!=1:
                        assert time.monotonic()-transition_began<1,('heat disappeared without mode transition',s)
                        time.sleep(.04);s=sample('confirm real mode transition');entry['samples'].append(s)
                    break
                assert s['mode']==0 and s['demand']==s['ao'][0]==501,s
                if s['switch'][0]==2:marks.setdefault(s['switch'][1],s['monotonic'])
                if time.monotonic()-heartbeat>=20:
                    print('AUTO GATE QUALIFY',label,s['switch'],s['running'],flush=True);heartbeat=time.monotonic();b.save()
                assert time.monotonic()-began<180,('automatic heat switch not observed',s)
                time.sleep(.08)
            assert all(i in marks for i in range(2,60)),marks
            elapsed=s['monotonic']-marks[2];assert 57.4<=elapsed<=58.7,elapsed
            e=dict(trigger=s,count2_to_trigger_s=elapsed)
            began=time.monotonic()
            while True:
                paused();s=sample('actual mode transition completes');entry['samples'].append(s)
                if s['mode']==s['active_mode']==1 and s['pending']==-1 and s['state'][9]==2 and all(v==0 for p in s['outdoor_status'] for v in p):break
                assert time.monotonic()-began<180,s
                time.sleep(.2)
            e['transition_complete']=s;return e
        e=dict(passed=False,runs=[],scope='Switch gates with accepted winter minimum normal parameters, raw room/fresh inputs; PID creation of exact ratio not qualified')
        b.log['cases']['T11-098']=e;b.save()
        for control in (() if counts_only else (0,1)):
            setup(control);r=dict(control_humidity=control,samples=[]);e['runs'].append(r)
            establish(1,500,r,'one actual cooling compressor ratio500')
            b.config({320:1});veto(65,1,500,r,'ratio500 equal QHB must not switch')
            b.config({346:501});r['qualified']=qualify(r,'ratio501 above QHB must switch after QHS60')
            b.stop();b.save()
        if not counts_only:
            e['passed']=True;b.record_local('T11-098',True,
                'V10.55恒温/控湿制冷分别测试：室温原始ADC输入25℃、新风-1℃，按用户接受的冬季最小输出[346]500/501形成精确再热需求，正常再热配置使真实压机保留1台。QHB0.5、500保持65s无切换且计时0；改501后重新连续QHS60转热并完成旧压机退出，两种控湿配置均验证。未写需求/PID/计时/输出；只证明切换门禁，不冒充PID自然生成500/501或物理端子。',e)
        else:
            # Do not replace prior completed ratio evidence with an empty run.
            del b.log['cases']['T11-098'];b.save()
        setup(0);b.gateway(1832,1);b.config({346:501});fixture.set(0,290)
        e=dict(passed=False,samples=[],scope='Two actual installed compressors versus one, normal gateway disable limits candidates; no feedback forcing')
        b.log['cases']['T11-099']=e;b.save()
        establish(2,501,e,'two genuine cooling feedback before gate test')
        b.config({320:1});veto(65,2,501,e,'two compressors veto despite ratio501')
        b.config({320:0});fixture.set(0,240)
        b.wait('genuine negative cooling error before two-to-one unload',lambda s:signed16(b.rd(511)[0])==240,10)
        b.wait('actual feedback falls from two to one by normal PID',
            lambda s:sum(v==2 for pair in s['outdoor_status'] for v in pair)==1,180)
        fixture.set(0,250)
        b.wait('neutral room for one-compressor switch gate',lambda s:signed16(b.rd(511)[0])==250,10)
        b.config({332:0});time.sleep(.3);b.config({332:1})
        establish(1,501,e,'normal room input unloads two to one')
        b.config({320:1});e['qualified']=qualify(e,'one compressor fresh QHS60 after neutral input')
        e['passed']=True;b.record_local('T11-099',True,
            'V10.55正常网关禁用外机1，室温原始ADC29℃使外机2两台真实制冷；新风-1℃、正常冬季最小输出501确保再热比>QHB0.5。启用自动切换后两台实际反馈保持65s，计时0且不切换；室温由29℃降至24℃形成真实减载，实际反馈降至1台后再回25℃保持，重新连续QHS60转热并完成压机退出。只模拟原始温度输入及正常参数，不改压机状态/需求/PID/计时；正式档和端子另验。',e)
        data=json.loads(RESULTS.read_text('utf8'))
        for cid in ('T11-098','T11-099'):
            data[cid]['inputs']='Raw room/fresh NTC ADC/filter INPUT simulation; accepted winter minimum and normal gateway configuration; no demand/feedback/timer forcing'
        dump(RESULTS,data)
    except BaseException:b.log['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.stop()
            if fixture:fixture.close();time.sleep(2)
        finally:b.finish()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);p.add_argument('--counts-only',action='store_true');a=p.parse_args()
    path=D/('auto_reheat_exact_controller_'+time.strftime('%H%M%S')+'.json');q=dict(started=now(),status='waiting_without_hardware',dependency=str(a.after));dump(path,q)
    try:
        while True:
            paused();prior=json.loads(a.after.read_text('utf8'))
            if prior.get('finished'):break
            time.sleep(3)
        assert prior.get('status')=='completed',prior
        restored_latest();q['status']='running';dump(path,q);run(a.counts_only);restored_latest();q['checks']=[]
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8')
            q['checks'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(path,q);assert proc.returncode==0
        q['status']='completed'
    except BaseException:q.update(status='stopped_on_error',error=traceback.format_exc());raise
    finally:q['finished']=now();dump(path,q)
