"""Exclusive live BENCH heat curves, using legal temperature calibration only.

Never writes demands, PID histories, outputs or protection timers. No calibration
outside the configured legal range. This does not qualify physical terminals.
"""
import os
os.environ.setdefault('PSC_BENCH_PACKAGE','.codex-tmp/fan_zero_target_v1052_v1239_20261105')
os.environ.setdefault('PSC_BENCH_INDOOR_VERSION','10.52')
import csv,json,time,traceback,argparse,hashlib
from pathlib import Path
from remaining571_common_20261105 import Bench,now
from run_indoor_bench_20261105 import D,R,RESULTS,dump,signed16,axf_symbols,BOARDS,I,ConnectHelper,loads_off
import run_indoor_bench_20261105 as runtime
if runtime.EXPECTED[2] in (53,54):runtime.EXPECTED[5]=6

LIMITS=f'V10.{runtime.EXPECTED[2]}/V12.39 BENCH板上正常调度；软件AO/DO回读，非端子电压/接点测量；正式时序另验。'

class HeatBench(Bench):
    def __init__(self,name):
        super().__init__('heat_dynamic_'+name+'_20261106')
        self.log.update(versions=self.rd(2622,18),profiles=self.rd(1298,2),
                        firmware_changed=False,output_or_pid_ram_writes=False,
                        input_overrides=[],limitations=LIMITS)
        self.sy=axf_symbols();self.swd=None
        # EEPROM readiness precedes SwitchStatusProcess's 20-second power-on
        # window. A command issued earlier is deliberately cleared at init.
        with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            began=time.monotonic();self.log['switch_startup_wait']=[]
            while True:
                uptime=ss.target.read32(self.sy['Systick_1ms'][0]);state=self.rd(700)[0]
                self.log['switch_startup_wait'].append({'at':now(),'uptime_ms':uptime,'system_state':state})
                if uptime>=21000 and state!=10:break
                assert time.monotonic()-began<30
                time.sleep(.3)
        self.save()

    def sample_heat(self,label):
        # Repeat demand/analog block around DO acquisition to reject scans that
        # straddle an actual PID tick. Rejected samples remain in the journal.
        for attempt in range(5):
            a=self.rd(872,72)
            contacts=self.rd(814,8)+self.rd(1366,8)
            z=self.rd(872,72)
            stable=a[18:20]==z[18:20] and a[42:52]==z[42:52]
            row={'at':now(),'t':time.monotonic(),'label':label,'heat':z[18],
                 'preheat':z[19],'ao':z[42:52],'do':contacts,
                 'ez':[signed16(x) for x in z[55:59]],'conflict':z[68],
                 'owner':z[69],'heat_state':z[70],'stable_read':stable}
            if not stable:
                self.log.setdefault('transition_reads',[]).append(row)
                continue
            self.log['samples'].append(row)
            return row
        raise AssertionError(('no coherent thermal snapshot',row))

    def temperature(self,ch,value):
        reg=495-ch;disp={0:511,1:510,2:512,3:513}[ch]
        old=signed16(self.rd(reg)[0]);actual=signed16(self.rd(disp)[0])
        wanted=old+value-actual
        assert -100<=wanted<=100,('NTC target outside legal calibration',ch,value,wanted)
        self.wr(reg,wanted)
        end=time.monotonic()+8
        while True:
            got=signed16(self.rd(disp)[0])
            if abs(got-value)<=1:break
            assert time.monotonic()<end,('temperature stimulus not settled',ch,value,got)
            time.sleep(.08)
        self.save()
        return got

    def finish(self):
        try:
            super().finish()
        finally:
            if self.swd is not None:self.swd.close();self.swd=None

    def record_local(self,cid,passed,actual,entry):
        self.log['cases'][cid]=entry;self.save()
        status='部分通过' if passed else '失败'
        data=json.loads(RESULTS.read_text('utf8')) if RESULTS.exists() else {}
        prior=data.get(cid,{})
        history=list(prior.get('history',[]))
        if prior:history.append({k:v for k,v in prior.items() if k!='history'})
        raw_input=bool(self.log.get('raw_ntc3_fixture'))
        if raw_input:actual='【NTC3原始ADC/滤波输入软件模拟】'+actual
        data[cid]={'status':status,'actual':actual,'evidence':str(self.path.relative_to(R)).replace('\\','/'),
            'restored':LIMITS+'本批恢复状态见证据末尾。','inputs':('NTC3原始ADC及滤波输入RAM模拟，其余合法校准；不写需求/PID/输出' if raw_input else '正常NTC合法校准及配置输入；不写需求/PID/输出'),
            'at':now(),'history':history}
        dump(RESULTS,data)
        p=R/'制热曲线_PID_板上续测_20261106.md'
        if not p.exists():p.write_text('# 制热曲线与PID板上续测（2026-11-06）\n\n'+LIMITS+'\n\n勾选表示已执行；部分通过仍缺端子/正式档证据。原失败历史保留。\n\n',encoding='utf8')
        line=f'- [x] **{cid} {status}**：{actual} [原始证据]({data[cid]["evidence"]})\n\n'
        with p.open('a',encoding='utf8') as f:f.write(line)
        with (R/'内机测试版逐项测试记录_20261105.md').open('a',encoding='utf8') as f:
            f.write('\n'+line)
        print('RECORDED',cid,status,actual,flush=True)

def config_heat(b,owner,kind):
    mode=1 if owner in ('main','preheat') else 0
    b.setup(mode)
    b.config({128:0,127:0,129:1,332:0,333:0,334:0,126:0,248:0,
        346:0,120:20,412:1,347:10,348:1,349:0,374:0,356:100,357:0,
        329:2,330:0,331:0,160:250,161:250,315:0,125:0})
    if owner=='main':b.config({128:kind+1})
    elif owner=='preheat':b.config({333:kind})
    else:b.config({128:0,127:1,129:1 if owner=='shared' else 0,332:kind})
    b.temperature(0,240);b.temperature(2,100)
    b.reset_faults();b.start()

def validate_curve(rows,kind,channel,slots,demand_key):
    bad=[];levels=set();regions=set();edges=[];prior=None;region=0;stage=0
    for s in rows:
        n=s[demand_key];groups=[s['do'][i] for i in slots]
        level=sum(x*(1<<i) for i,x in enumerate(groups));levels.add(level)
        a=s['ao'][channel]
        if kind==1:ok=a==n and level==0
        elif kind in (2,3):
            # These numeric thresholds are a regression cross-check of the
            # current implementation, not invented labels on the spec graph.
            up=(170,500,830) if kind==2 else (75,225,375,525,675,825,950)
            down=(0,330,660) if kind==2 else (0,150,300,450,600,750,900)
            for _ in range(8):
                nxt=stage
                if stage<len(up) and n>up[stage]:nxt=stage+1
                elif stage>0 and (n<=0 if stage==1 else n<down[stage-1]):nxt=stage-1
                if nxt==stage:break
                stage=nxt
            ok=a==0 and level==stage
        else:
            if n==0:region=0
            elif region==0 and n>400:region=1
            elif region==1:
                if n>700:region=2
                elif n<300:region=0
            elif region==2 and n<600:region=1
            g=[int(region>=1 and n>0),int(region>=2 and n>0),0]
            want=(max(0,min(400,n-300*g[0]-300*g[1]))*1000+200)//400
            regions.add(region);ok=groups==g and a==want
        if not ok:bad.append({'sample':s,'expected_region':region})
        key=(level if kind in (2,3,4) else None)
        if key!=prior:
            edges.append({'demand':n,'direction':s['direction'],'level':level,'ao':a,'t':s['t']})
            prior=key
    for direction in ('up','down'):
        ns=[s[demand_key] for s in rows if s['direction']==direction]
        if not ns or not (max(ns)==1000 if direction=='up' else min(ns)==0):
            bad.append({'missing_endpoint':direction})
        if kind in (2,3):
            observed={sum(s['do'][j]*(1<<i) for i,j in enumerate(slots)) for s in rows if s['direction']==direction}
            if observed!=set(range(2**kind)):
                bad.append({'direction':direction,'missing_stage_plateaus':sorted(set(range(2**kind))-observed)})
    if kind in (2,3) and levels!=set(range(2**kind)):
        bad.append({'missing_levels':sorted(set(range(2**kind))-levels)})
    if kind==4 and regions!={0,1,2}:bad.append({'missing_scr_regions':sorted({0,1,2}-regions)})
    return {'passed':not bad,'mismatches':bad,'levels':sorted(levels),'edges':edges,
        'numeric_stage_regression_threshold_source':'current source, not complete original-graph labels',
        'stage_thresholds':'observed, not invented specification numbers'}

def curves(owners,kinds=(1,2,3,4)):
    b=HeatBench('curves');any_failure=False
    try:
        for owner in owners:
            for kind in kinds:
                start={'main':7,'shared':11,'independent':15,'preheat':19}[owner]
                cid=f'T06-{start+kind-1:03d}'
                print('START',cid,owner,kind,flush=True)
                entry={'owner':owner,'output_mode':kind,'started':now(),'rows':[]}
                b.log['cases'][cid]=entry;b.save()
                try:
                    config_heat(b,owner,kind)
                    channel=1 if owner=='preheat' else 9 if owner=='independent' else 0
                    slots=(13,14,15) if owner=='preheat' else (0,1,2)
                    key='preheat' if owner=='preheat' else 'heat'
                    if owner=='preheat':
                        # Normal 0.1 C calibration: 10..0 C maps 0..100%.
                        # Add dense samples around every code transition and
                        # the explicitly specified SCR 30/40/60/70% boundaries.
                        ns=sorted(set(range(0,1001,50))|{10,70,80,160,170,180,220,230,290,300,310,320,330,340,
                            370,380,390,400,410,440,450,460,490,500,510,520,530,590,600,610,650,660,670,680,
                            690,700,710,740,750,760,820,830,840,890,900,910,940,950,960,990})
                        for direction,points in (('up',ns),('down',list(reversed(ns)))):
                            for n in points:
                                b.temperature(2,100-n//10)
                                # Allow sensor conversion, controller and output
                                # scheduler to settle before coherent acquisition.
                                time.sleep(.16)
                                for _ in range(2):
                                    s=b.sample_heat(cid);s['direction']=direction;entry['rows'].append(s)
                            b.save()
                    else:
                        for direction,temp,endpoint in (('up',240,1000),('down',260,0)):
                            if direction=='down' and kind!=1:
                                # Reduce only the allowed PID gain during the
                                # sign reversal so a proportional kick cannot
                                # skip the first unloading plateau.
                                b.config({347:1})
                            b.temperature(0,temp);began=time.monotonic();last=None
                            reversal_completed=False
                            while True:
                                s=b.sample_heat(cid);s['direction']=direction;entry['rows'].append(s)
                                signature=(s[key],tuple(s['do'][i] for i in slots),s['ao'][channel])
                                if signature!=last:
                                    print('CURVE',cid,direction,round(time.monotonic()-began,2),*signature,flush=True);last=signature
                                if s[key]==endpoint:
                                    time.sleep(.2);s=b.sample_heat(cid);s['direction']=direction;entry['rows'].append(s);break
                                if direction=='down' and kind!=1 and s[key]<1000 and not reversal_completed:
                                    b.config({347:10});reversal_completed=True
                                assert time.monotonic()-began<180,('ramp endpoint timeout',s)
                                time.sleep(.06)
                            b.save()
                    entry['assessment']=validate_curve(entry['rows'],kind,channel,slots,key)
                    # Unselected heat AO and third SCR contactor must stay off.
                    used={channel}
                    entry['other_heat_ao_zero']=all(all(s['ao'][i]==0 for i in {0,1,9}-used) for s in entry['rows'])
                    passed=entry['assessment']['passed'] and entry['other_heat_ao_zero']
                    entry['passed']=passed;any_failure|=not passed
                    b.record_local(cid,passed,
                        f'{owner}方式{kind}：板上升降需求覆盖0～1000，{len(entry["rows"])}组稳定样本；档位{entry["assessment"]["levels"]}；'
                        f'曲线核对异常{len(entry["assessment"]["mismatches"])}，其它热AO清零={entry["other_heat_ao_zero"]}。分段切换点见证据edges。',entry)
                except Exception:
                    entry['error']=traceback.format_exc();b.save();any_failure=True
                    b.record_local(cid,False,entry['error'].splitlines()[-1],entry)
                    raise
                finally:b.stop()
        b.log['all_selected_curves_passed']=not any_failure
    finally:
        b.finish()
        print('RESTORED',b.log.get('restored'),b.path,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['curves']);p.add_argument('--owners',nargs='+',default=['main','shared','independent','preheat']);p.add_argument('--kinds',nargs='+',type=int,default=[1,2,3,4])
    args=p.parse_args();curves(args.owners,args.kinds)
