"""Live allocation with replayed received runtime INPUT fields.

Only UnitReadStatus runtime report fields are simulated. Outdoor persistent
runtime counters, compressor status/commands, demands, output and timers are
not written. This cannot qualify cumulative-time measurement/persistence.
"""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench,paused
import struct,threading,sys,subprocess


class RuntimeReports:
    def __init__(self,b,input_fixture=None):
        from elftools.elf.elffile import ELFFile
        from elftools.dwarf.dwarf_expr import DWARFExprParser
        with (I/(BOARDS[2][-1]+'.axf')).open('rb') as f:
            elf=ELFFile(f);expr=DWARFExprParser(elf.get_dwarf_info().structs)
            for cu in elf.get_dwarf_info().iter_CUs():
                for die in cu.iter_DIEs():
                    n=die.attributes.get('DW_AT_name')
                    if die.tag=='DW_TAG_structure_type' and n and n.value==b'UNIT_STATUS_STRU_Read' and 'DW_AT_byte_size' in die.attributes:
                        self.stride=die.attributes['DW_AT_byte_size'].value;self.offsets={}
                        for v in die.iter_children():
                            if v.tag!='DW_TAG_member':continue
                            a=v.attributes['DW_AT_data_member_location'];value=a.value
                            if not isinstance(value,int):
                                ops=expr.parse_expr(value);assert len(ops)==1 and ops[0].op_name=='DW_OP_plus_uconst';value=ops[0].args[0]
                            self.offsets[v.attributes['DW_AT_name'].value.decode()]=value
                        break
                if hasattr(self,'stride'):break
        self.b=b;self.error=None;self.inputs={};self.lock=threading.Lock();self.event=threading.Event()
        self.input_fixture=input_fixture;self.base=b.sy['UnitReadStatus'][0]
        if input_fixture is None:
            self.ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            self.ss.open();self.t=self.ss.target
        b.log['runtime_report_input_fixture']=dict(base=self.base,stride=self.stride,fields={k:self.offsets[k] for k in ('CompTotalRunSeconds','OutdoorTotalRunSeconds')},
            statement='Received runtime-report INPUT simulation only; outdoor counters and every status/command/output remain unmodified',events=[])
        if input_fixture is None:
            self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()

    def set(self,short_unit,difference,short_comp=0):
        values={}
        for m in (1,2):
            base=self.base+self.stride*m
            values[base+self.offsets['OutdoorTotalRunSeconds']]=struct.pack('<I',20000-difference if m==short_unit else 20000)
            values[base+self.offsets['CompTotalRunSeconds']]=struct.pack('<2I',*([100,1000] if short_comp==0 else [1000,100]))
        with self.lock:self.inputs=values
        if self.input_fixture is not None:
            with self.input_fixture.lock:self.input_fixture.extra_inputs=values
        self.b.log['runtime_report_input_fixture']['events'].append(dict(at=now(),short_unit=short_unit,difference=difference,short_compressor=short_comp+1))
        self.b.save()

    def loop(self):
        try:
            while not self.event.is_set():
                with self.lock:values=dict(self.inputs)
                for a,v in values.items():self.t.write_memory_block8(a,list(v))
                self.t.flush();self.event.wait(.008)
        except BaseException:self.error=traceback.format_exc()

    def close(self):
        if self.input_fixture is not None:
            with self.input_fixture.lock:self.input_fixture.extra_inputs={}
            self.b.log['runtime_report_input_fixture'].update(stopped=now(),error=self.input_fixture.error)
            self.b.save();assert not self.input_fixture.error,self.input_fixture.error
            return
        self.event.set();self.thread.join(5);assert not self.thread.is_alive()
        self.ss.close();self.b.log['runtime_report_input_fixture'].update(stopped=now(),error=self.error);self.b.save();assert not self.error,self.error


def run():
    b=CheckedBench('runtime_selection_report_inputs');fixture=None
    try:
        fixture=RuntimeReports(b)
        for i,(diff,short) in enumerate((d,s) for d in (7199,7200,7201) for s in (1,2)):
            paused();cid=f'T10-{4+i:03d}';expected=short if diff>7200 else 1
            b.setup(0);b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
                160:250,161:250,315:1,327:1,316:350,317:220,318:0,319:120,
                320:0,346:0,245:1,247:0,329:2,330:0,331:0,365:1,411:200,10:500,12:500})
            b.temperature(0,250);b.temperature(2,230);fixture.set(short,diff);b.reset_faults();time.sleep(.5)
            e=dict(passed=False,difference=diff,short_unit=short,expected_selected_unit=expected,samples=[],
                scope='Live control board, received runtime fields simulated; real load commands/316 outputs/status, not cumulative-time validation')
            b.log['cases'][cid]=e;b.save();b.wr(398,1);began=time.monotonic();heartbeat=began;stable=None
            while True:
                paused();s=b.snapshot('runtime input allocation');s.update(target_count=b.rd(881)[0],actual_count=b.rd(119)[0]);e['samples'].append(s)
                assert not any(s['faults']),s
                active=[(m+1,c+1) for m,pair in enumerate(s['outdoor_status']) for c,v in enumerate(pair) if v==2]
                if active:
                    assert active==[(expected,1)],('runtime selection mismatch',diff,short,active,expected,s)
                    if stable is None:stable=time.monotonic()
                    if time.monotonic()-stable>=5 and s['target_count']==s['actual_count']==1:break
                if time.monotonic()-heartbeat>=20:
                    print('RUNTIME INPUT SELECT',cid,diff,short,round(time.monotonic()-began,1),s['outdoor_status'],flush=True);heartbeat=time.monotonic();b.save()
                assert time.monotonic()-began<220,('target1 did not establish',s)
                time.sleep(.15)
            e['passed']=True;b.record_local(cid,True,
                f'V10.55接收侧UnitReadStatus仅模拟两外机累计秒数差{diff}s，较短为外机{short}，压机接收累计设100/1000；环温23℃经正常公式给目标1，真实指令与316反馈最终仅外机{expected}/压机1制冷，保持5s。差<=7200按序号、>7200按较短外机；未改316持久计时/状态/输出或330需求/PID/保护计时。接收报文输入回放，不当作实际累计时长测量。',e)
            data=json.loads(RESULTS.read_text('utf8'));data[cid]['inputs']='Received UnitReadStatus runtime-report fields simulated only; real commands and feedback';dump(RESULTS,data)
            b.stop()
        b.log['all_six_selection_inputs_passed']=True;b.save()
    except BaseException:b.log['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.stop()
            if fixture:fixture.close();time.sleep(12)
        finally:b.finish()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    dep=a.after;path=D/('runtime_selection_controller_'+time.strftime('%H%M%S')+'.json');q=dict(started=now(),status='waiting_without_hardware',dependency=str(dep),ventilation='Deferred by user');dump(path,q)
    try:
        while True:
            paused();d=json.loads(dep.read_text('utf8'))
            if d.get('finished'):break
            time.sleep(3)
        assert d.get('status')=='completed',d
        from nonvent_supplement_v1055_20261109 import restored_latest
        restored_latest();q['status']='running';dump(path,q);run()
        q['checks']=[]
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8')
            q['checks'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(path,q);assert proc.returncode==0
        q['status']='completed'
    except BaseException:q.update(status='stopped_on_error',error=traceback.format_exc());raise
    finally:q['finished']=now();dump(path,q)
