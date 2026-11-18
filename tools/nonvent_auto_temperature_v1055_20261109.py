"""Real QHS=60 temperature switching, no timer or demand injection."""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench, paused
from nonvent_supplement_v1055_20261109 import restored_latest
import subprocess, sys, struct


def run(mode,humidity):
    b=CheckedBench('auto_temperature_'+str(mode)+'_'+str(humidity));ss=None
    ids=['T11-089','T11-095','T11-103'] if mode==0 else ['T11-093'] if humidity else ['T11-092','T11-096']
    e=dict(passed=False,mode=mode,humidity=humidity,phases=[],ram_state_writes=False,
        scope='Actual QHS60 counter and normal mode exit/start; legal room calibration; no electrical/terminal/PRODUCTION acceptance')
    for cid in ids:b.log['cases'][cid]=e
    b.save()
    try:
        b.setup(mode);b.config({128:0,127:0,332:0,333:0,334:1 if humidity else 0,
            125:int(humidity),126:int(humidity),248:int(humidity),
            160:250,161:250,162:500,120:20,361:200,412:1,
            320:0,321:50,322:60,315:0,346:0,245:1,247:0,
            329:2,330:0,331:0,386:0})
        if humidity:b.ai(1,500)
        b.temperature(0,250);b.reset_faults();b.start()
        ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target;destination=1-mode
        def sample(label):
            s=b.snapshot(label);d=b.rd(872,22)
            s.update(mode=b.rd(236)[0],room_temp10=signed16(b.rd(511)[0]),humidity=b.rd(501)[0],
                switch_direction=d[11],switch_count=d[12],heat_demand=d[18],humidity_demand=d[20],
                active=t.read8(b.sy['IndoorActiveWorkMode'][0]),
                pending=struct.unpack('<i',struct.pack('<I',t.read32(b.sy['IndoorPendingWorkMode'][0])))[0])
            return s
        def hold(label,temp,seconds):
            b.temperature(0,temp);p=dict(label=label,temperature=temp,seconds=seconds,samples=[]);e['phases'].append(p)
            began=time.monotonic();heartbeat=began
            while time.monotonic()-began<seconds:
                paused();s=sample(label);p['samples'].append(s)
                assert not any(s['faults']) and s['state'][9]==2,s
                assert s['room_temp10']==temp,('Exact input boundary not maintained',s)
                assert s['mode']==mode and s['active']==mode and s['pending']==-1 and s['switch_count']==0,s
                if time.monotonic()-heartbeat>=25:
                    print('AUTO TEMP HOLD',mode,humidity,label,round(time.monotonic()-began,1),flush=True);heartbeat=time.monotonic();b.save()
                time.sleep(.15)
            p.update(passed=True,observed_s=time.monotonic()-began);b.save()
        b.config({320:1})
        if mode==0:hold('compressors already off while room neutral',250,65)
        hold('exact temperature boundary must not qualify',240 if mode==0 else 260,65)
        requested=239 if mode==0 else 261
        b.temperature(0,requested);p=dict(label='strict temperature qualifies QHS60',samples=[],marks={});e['phases'].append(p)
        began=time.monotonic();heartbeat=began
        while True:
            paused();s=sample(p['label']);p['samples'].append(s)
            assert not any(s['faults']) and s['room_temp10']==requested,s
            p['marks'].setdefault(s['switch_count'],s['monotonic'])
            if s['pending']==destination or s['mode']==destination:p['trigger']=s;break
            assert s['mode']==mode and s['active']==mode and s['pending']==-1,s
            assert s['heat_demand']==s['humidity_demand']==0,s
            assert time.monotonic()-began<64,('auto temperature switch not observed',s)
            if time.monotonic()-heartbeat>=20:
                print('AUTO TEMP COUNT',mode,humidity,s['switch_count'],flush=True);heartbeat=time.monotonic();b.save()
            time.sleep(.08)
        assert all(n in p['marks'] for n in range(2,60)),('QHS evidence missed count',p['marks'].keys())
        p['count2_to_trigger_s']=s['monotonic']-p['marks'][2]
        assert 57.5<=p['count2_to_trigger_s']<=58.5,p['count2_to_trigger_s']
        p['transition']=[];began=time.monotonic();heartbeat=began
        while True:
            paused();s=sample('normal auto mode transition');p['transition'].append(s)
            assert not any(s['faults']),s
            if s['mode']==s['active']==destination and s['pending']==-1 and s['state'][9]==2:break
            assert time.monotonic()-began<170,('normal mode transition incomplete',s)
            if time.monotonic()-heartbeat>=25:
                print('AUTO TEMP TRANSITION',mode,humidity,s['mode'],s['active'],s['pending'],s['state'][9],flush=True);heartbeat=time.monotonic();b.save()
            time.sleep(.15)
        e.update(passed=True,completed=now());b.save()
        text=(f'V10.55模式{mode}、控湿{int(humidity)}，WD25/WDF2；'+
            ('压机全停而室温25℃保持65s不切换；24.0℃等号保持65s不计时，23.9℃后重新完整计QHS60转热，说明当前实现为低温与全停共同连续60s（原文两种计时解释仍保留）；' if mode==0 else
             '室温26.0℃等号保持65s不计时，26.1℃且制热已关后完整计QHS60转冷；'+('回风湿度约50%，未满足高湿分支，观察的是高温分支；' if humidity else '无控湿；'))+
            f'计数2至触发{p["count2_to_trigger_s"]:.3f}s，旧模式退出至新模式步骤2闭环。合法NTC校准，未写计时/PID/需求/输出，实际温湿度信号与端子另验。')
        for cid in ids:b.record_local(cid,True,text,e)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:
        if ss:ss.close()
        b.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    dep=a.after.resolve();journal=D/('nonvent_auto_temperature_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),dependency=dep.relative_to(R).as_posix(),status='waiting_without_hardware',actions=[],ventilation='Deferred by user');dump(journal,q)
    while True:
        paused()
        try:previous=json.loads(dep.read_text('utf8'))
        except (OSError,ValueError):previous={}
        if previous.get('finished'):break
        time.sleep(3)
    assert previous.get('status')=='completed',previous
    restored_latest();q['status']='running';dump(journal,q)
    try:
        for mode,humidity in ((0,False),(1,False),(1,True)):
            paused();restored_latest();row=dict(mode=mode,humidity=humidity,started=now(),status='running');q['actions'].append(row);dump(journal,q)
            try:run(mode,humidity);row['status']='finished_see_per_case_scope'
            except Exception:
                row.update(status='failed_or_unavailable',error=traceback.format_exc());dump(journal,q);restored_latest()
            row['finished']=now();dump(journal,q)
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=300)
            q['actions'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(journal,q)
            assert proc.returncode==0,(script,proc.stderr)
        q['status']='completed'
    finally:q['finished']=now();dump(journal,q)
    print('NONVENT AUTO TEMPERATURE FINISHED',journal,flush=True)


if __name__=='__main__':main()
