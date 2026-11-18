"""Real 330/316 defrost state transitions, isolated compressor-power bench.

Only legacy HMI command INPUTS and (HP case) the 316 DI polarity setting are
written via exact-image SWD. Lifecycle, outputs, demands, PID and timers are not.
"""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench,paused
from nonvent_supplement_v1055_20261109 import restored_latest
from remaining529_manual_defrost_input_20261105 import manual_defrost
import subprocess,sys


class DefrostBench(CheckedBench):
    def __init__(self,name):
        super().__init__('defrost_nonvent_'+name);self.gateway_original={};self.outss=None
        from elftools.elf.elffile import ELFFile
        with (I/(BOARDS[0][-1]+'.axf')).open('rb') as f:
            self.outsy={s.name:(s['st_value'],s['st_size']) for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols() if s.name}
        self.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        self.outss.open();self.ot=self.outss.target
        self.hp_original=self.ot.read16(self.outsy['Parameter'][0]+4)
        self.log.update(stimulus='Legacy HMI defrost command words; normal configuration and optional HP polarity',
            raw_high_pressure_contact_tested=False,lifecycle_or_timer_writes=False,
            outdoor_hp_polarity_before=self.hp_original);self.save()

    def gateway(self,a,value):
        if a not in self.gateway_original:self.gateway_original[a]=self.rd(a)[0]
        state=1830+((a-1830)//48)*48+43;began=time.monotonic()
        while self.rd(state)[0]==1:
            assert time.monotonic()-began<45,('gateway busy',a)
            time.sleep(.2)
        if self.rd(a)[0]==value:return
        event=dict(address=a,value=value,before=self.rd(a)[0],started=now());self.log.setdefault('gateway_writes',[]).append(event);self.save()
        self.c.write_single_register(1,a,value);began=time.monotonic()
        while True:
            actual=self.rd(a)[0];status=self.rd(state)[0]
            if actual==value and status!=1:break
            assert time.monotonic()-began<50,('gateway confirmation',a,actual,status)
            time.sleep(.2)
        # Verify the value at the destination instead of trusting an echo.
        target=165+(a-1830)%48
        destination=signed16(self.ot.read16(self.outsy['Parameter'][0]+target*2))
        assert destination==value,('destination mismatch',a,target,value,destination)
        event.update(finished=now(),readback=actual,status=status,destination_parameter=target,destination_value=destination);self.save()

    def sample(self,label):
        s=self.snapshot(label);s.update(phase=self.rd(1550,2),heat_demand=self.rd(890)[0],
            actual_count=self.rd(119)[0],target_count=self.rd(881)[0],
            indoor_eev_targets=self.rd(1145,8),indoor_eev_actual=self.rd(1153,8),
            outdoor_comp=list(self.ot.read_memory_block8(self.outsy['Comp'][0],2)),
            hp_input=self.ot.read8(self.outsy['X_00'][0]),
            hp_alarms=[self.ot.read16(self.outsy['Parameter'][0]+606*2),self.ot.read16(self.outsy['Parameter'][0]+607*2)])
        return s

    def until(self,label,predicate,timeout):
        began=time.monotonic();rows=[];heartbeat=began
        while True:
            paused();s=self.sample(label);rows.append(s)
            if predicate(s):self.save();return s,rows
            assert time.monotonic()-began<timeout,(label,s)
            if time.monotonic()-heartbeat>=20:
                print('DEFROST',label,round(time.monotonic()-began,1),s['phase'],s['outdoor_comp'],s['state'][9],flush=True);heartbeat=time.monotonic();self.save()
            time.sleep(.1)

    def prepare(self):
        self.setup(1)
        self.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,
            315:0,327:1,160:250,161:250,120:20,412:1,
            426:100,427:1,428:0,347:100,348:1,349:0,
            346:0,320:0,245:1,247:0,329:2,330:0,331:0,
            365:1,372:350,10:500,12:500})
        self.temperature(0,220);self.reset_faults()
        self.gateway(1856,2);self.gateway(1857,2)
        self.start();s,rows=self.until('all four actual heat feedback',lambda s:all(v==3 for pair in s['outdoor_status'] for v in pair),180)
        self.log['full_heat_precondition']=dict(final=s,samples=rows);self.wr(540,1)
        manual_defrost(self,True)
        s,rows=self.until('both circuits active defrost8',lambda s:s['phase']==[8,8] and s['outdoor_comp']==[1,1],65)
        self.log['active_defrost_precondition']=dict(final=s,samples=rows);self.save();return s

    def finish(self):
        try:
            if self.outss:
                self.ot.write16(self.outsy['Parameter'][0]+4,self.hp_original);self.ot.flush()
                if any(v in (7,8) for v in self.rd(1550,2)):
                    manual_defrost(self,False)
                    self.until('cleanup ends defrost lifecycle',lambda s:s['phase']==[0,0],150)
            self.stop()
            for a,v in self.gateway_original.items():self.gateway(a,v)
            self.log['gateway_restored']={str(a):self.rd(a)[0]==v for a,v in self.gateway_original.items()}
            self.log['hp_polarity_restored']=self.ot.read16(self.outsy['Parameter'][0]+4)==self.hp_original
            assert all(self.log['gateway_restored'].values()) and self.log['hp_polarity_restored'];self.save()
        except BaseException:
            # Keep input/gateway cleanup failure visible even if the ordinary
            # indoor parameter restoration below can complete successfully.
            self.log['cleanup_error']=traceback.format_exc();self.save();raise
        finally:
            if self.outss:self.outss.close();self.outss=None
            super().finish()


def run(kind):
    b=DefrostBench(kind);cid={'recovery-stop':'T16-003','demand':'T16-004','emergency':'T16-005','raw-hp1':'T16-006'}[kind]
    e=dict(passed=False,kind=kind,samples=[],scope='BENCH5s recovery and software outputs; no physical HP/terminals or formal60s')
    b.log['cases'][cid]=e;b.save()
    try:
        e['active']=b.prepare()
        if kind=='recovery-stop':
            manual_defrost(b,False)
            s,rows=b.until('normal stop during actual recovery7',lambda s:s['phase']==[7,7],60)
            e['recovery_entry']=s;e['to_recovery']=rows;b.wr(398,0);began=time.monotonic();seen=[]
            while True:
                paused();s=b.sample('recovery normal-stop closure');e['samples'].append(s)
                if s['phase']==[7,7]:
                    seen.append(s);assert s['state'][9]!=0,('lifecycle7 released stop gate early',s)
                if s['phase']==[0,0] and s['state'][9]==0 and loads_off(s):break
                assert time.monotonic()-began<180,('normal stop during recovery incomplete',s)
                time.sleep(.1)
            assert seen,'No actual recovery7 sample after stop command'
            e['passed']=True
            text='真实制热及化霜8建立，旧HMI退出命令后实际采到恢复7，再发正常关机；7仍在时未提前宣布步骤0，最终生命周期0且正常停机、负载软件输出清零。恢复档为BENCH5s，不代表正式60s。'
        elif kind=='demand':
            for temp,reheat,target,label in ((280,0,0,'reduce total demand while defrost8'),(220,1,4,'increase total demand while defrost8')):
                b.config({127:reheat});b.temperature(0,temp)
                s,rows=b.until(label,lambda s:s['target_count']==target and s['phase']==[8,8],25)
                e.setdefault('phases',[]).append(dict(label=label,settling=rows,hold=[]));began=time.monotonic()
                while time.monotonic()-began<6:
                    paused();s=b.sample(label);e['phases'][-1]['hold'].append(s)
                    assert s['phase']==[8,8] and s['outdoor_comp']==[1,1] and s['target_count']==target,s
                    time.sleep(.1)
                b.save()
            manual_defrost(b,False);e['ended'],e['end_samples']=b.until('demand case normal defrost end',lambda s:s['phase']==[0,0],90)
            e['passed']=True
            text='真实化霜8期间，合法室温28℃/禁用再热令总目标降至0，再以22℃/启用再热令目标升至4；各保持6s，对应外机仍化霜8、两台Comp软件输出保持1，普通加减载未抢占该外机；正常退出后生命周期清0。本子范围为8阶段，7阶段的加减需求组合另验。'
        elif kind=='emergency':
            b.wr(156,1-b.polarities[156]);e['fire'],e['fire_samples']=b.until('fire emergency during actual defrost8',lambda s:s['state'][9]==0 and loads_off(s) and s['outdoor_comp']==[0,0],15)
            assert b.rd(605)[0]==1
            b.wr(156,b.polarities[156]);e['signal_restored']=b.sample('fire signal returned latch remains');assert b.rd(605)[0]==1
            b.reset_faults();b.wr(398,0);e['passed']=True
            text='真实化霜8期间以正常消防DI极性模拟故障；330停到步骤0、室内AO/DO软件负载清零，316两台Comp软件输出也关闭；输入恢复后仍锁存，正常524复位。仅8阶段消防组合，7阶段与其它急停输入仍需另验。'
        else:
            addr=b.outsy['Parameter'][0]+4;assert e['active']['hp_input']==0
            began=time.monotonic();e['polarity_write']=dict(address=addr,parameter=2,width=2,value=1-b.hp_original,at=now())
            b.ot.write16(addr,1-b.hp_original);b.ot.flush()
            try:
                while True:
                    paused();s=b.sample('defrost raw HP1 polarity input');e['samples'].append(s)
                    if s['hp_input']==1 and s['outdoor_comp'][0]==0:
                        assert s['outdoor_comp'][1]==1 and s['phase']==[8,8] and s['hp_alarms']==[0,0],s
                        e['trip']=s;e['observed_reaction_s']=time.monotonic()-began;break
                    assert time.monotonic()-began<3,('defrost HP1 did not isolate the corresponding circuit',s)
                    time.sleep(.03)
            finally:b.ot.write16(addr,b.hp_original);b.ot.flush()
            began=time.monotonic();e['hold']=[]
            while time.monotonic()-began<2:
                s=b.sample('HP input healthy, participant remains ended');e['hold'].append(s)
                assert s['outdoor_comp']==[0,1] and s['phase']==[8,8],s
                time.sleep(.1)
            manual_defrost(b,False);e['ended'],e['end_samples']=b.until('HP1 normal defrost completion',lambda s:s['phase']==[0,0],90)
            e['passed']=True
            text=f'真实化霜8时仅翻转316[2]高压DI极性设置，经原始X00检测约{e["observed_reaction_s"]:.3f}s仅关闭压机1，压机2保留，未锁存新高压报警；恢复极性后观察2s压机1不重启，正常退出生命周期清0。为GPIO极性输入模拟，非真实高压接点/压力或端子测量。'
        b.record_local(cid,True,'V10.55/V12.39：'+text+' 所有输入、网关设置及参数在批次末恢复；不写状态、输出、PID、需求或计时RAM。',e)
        records=json.loads(RESULTS.read_text('utf8'));records[cid]['inputs']=b.log['stimulus'];dump(RESULTS,records)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:b.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True)
    p.add_argument('--kinds',nargs='+',choices=('recovery-stop','demand','emergency','raw-hp1'),default=('recovery-stop','demand','emergency','raw-hp1'))
    a=p.parse_args()
    dep=a.after.resolve();journal=D/('nonvent_defrost_controller_'+time.strftime('%H%M%S')+'.json')
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
        for kind in a.kinds:
            paused();restored_latest();row=dict(kind=kind,started=now(),status='running');q['actions'].append(row);dump(journal,q)
            try:run(kind);row['status']='finished_see_per_case_scope'
            except Exception:
                row.update(status='failed_or_unavailable',error=traceback.format_exc());dump(journal,q);restored_latest()
            row['finished']=now();dump(journal,q)
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=300)
            q['actions'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(journal,q)
            assert proc.returncode==0,(script,proc.stderr)
        q['status']='completed'
    finally:q['finished']=now();dump(journal,q)
    print('NONVENT DEFROST FINISHED',journal,flush=True)


if __name__=='__main__':main()
