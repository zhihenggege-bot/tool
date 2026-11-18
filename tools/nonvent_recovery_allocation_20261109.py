"""Actual defrost 8/7 excludes ordinary allocation; every state is read-only."""
from nonvent_eev_pair_live_20261109 import *
from nonvent_supplement_v1055_20261109 import restored_latest
from remaining529_manual_defrost_input_20261105 import manual_defrost
from elftools.elf.elffile import ELFFile
from elftools.dwarf.dwarf_expr import DWARFExprParser
import subprocess, sys


def command_layout():
    with (I/(BOARDS[2][-1]+'.axf')).open('rb') as f:
        elf=ELFFile(f);di=elf.get_dwarf_info();expr=DWARFExprParser(di.structs)
        for cu in di.iter_CUs():
            for die in cu.iter_DIEs():
                name=die.attributes.get('DW_AT_name')
                if die.tag!='DW_TAG_structure_type' or not name or name.value!=b'UNIT_STATUS_STRU_Write' or 'DW_AT_byte_size' not in die.attributes:continue
                stride=die.attributes['DW_AT_byte_size'].value
                for member in die.iter_children():
                    n=member.attributes.get('DW_AT_name')
                    if member.tag=='DW_TAG_member' and n and n.value==b'CompControl':
                        offset=member.attributes['DW_AT_data_member_location'].value
                        if not isinstance(offset,int):offset=expr.parse_expr(offset)[0].args[0]
                        return stride,offset
    raise AssertionError('Exact-image compressor command layout not found')


def run():
    b=PairedBench('recovery_allocation_readonly');ss=None
    eight=dict(passed=False,runs=[],scope='Actual first outdoor defrost8 at targets0/4; software commands/feedback only')
    seven=dict(passed=False,runs=[],scope='Actual first outdoor recovery7, BENCH5s at targets0/4; not formal60s or terminals')
    b.log['cases'].update({'T10-018':eight,'T10-019':seven});b.save()
    try:
        stride,offset=command_layout()
        b.log['read_only_command_layout']=dict(symbol=b.sy['UnitWriteStatus'],stride=stride,comp_control_offset=offset,word_bytes=4)
        def sample(label):
            s=b.sample(label)
            s['ordinary_commands']=[list(struct.unpack('<2I',bytes(it.read_memory_block8(b.sy['UnitWriteStatus'][0]+m*stride+offset,8)))) for m in (1,2)]
            return s
        for target,temp,reheat in ((0,280,0),(4,220,1)):
            if ss:ss.close();ss=None
            b.prepare();b.config({127:reheat});b.temperature(0,temp)
            b.until('actual defrost8 requested target'+str(target),lambda s:s['phase']==[8,8] and s['target_count']==target,30)
            ss=ConnectHelper.session_with_chosen_probe(blocking=False,unique_id=BOARDS[2][1],target_override=BOARDS[2][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            assert ss is not None,'330 probe unavailable for read-only command observation'
            ss.open();it=ss.target
            r=dict(target=target,samples=[],passed=False);eight['runs'].append(r)
            began=time.monotonic();commands=None
            while time.monotonic()-began<3:
                paused();s=sample('actual8 ordinary allocation must leave owner unchanged');r['samples'].append(s)
                assert s['phase']==[8,8] and s['target_count']==target and s['outdoor_comp']==[1,1] and not any(s['faults']),s
                if commands is None:commands=s['ordinary_commands'][0]
                assert s['ordinary_commands'][0]==commands,('ordinary commands changed during8',s,commands)
                time.sleep(.06)
            r['passed']=True;b.save()
            z=dict(target=target,before_commands=commands,samples=[],passed=False);seven['runs'].append(z)
            # Share this existing session for the short HMI INPUT transaction.
            # No concurrent SWD users or duplicate probe acquisition.
            manual_defrost(b,False,session=ss);began=time.monotonic();first=None;last=None
            while True:
                paused();s=sample('actual recovery7 ordinary allocation must leave owner unchanged');z['samples'].append(s)
                assert not any(s['faults']),s
                if s['phase']==[7,7]:
                    if first is None:first=s['monotonic']
                    last=s['monotonic']
                    assert s['target_count']==target and s['outdoor_comp']==[0,0],s
                    assert s['ordinary_commands'][0]==commands,('ordinary commands changed during7',s,commands)
                if first is not None and s['phase']==[0,0]:break
                assert time.monotonic()-began<90,('recovery lifecycle incomplete',s)
                time.sleep(.04)
            assert first is not None and last-first>=2.5,('insufficient actual7 observation',first,last)
            z.update(passed=True,observed_both_recovery_s=last-first);b.save()
            print('ACTUAL RECOVERY ALLOCATION',target,'PASS',round(last-first,3),commands,flush=True)
            b.stop()
        for cid,e in (('T10-018',eight),('T10-019',seven)):
            e['passed']=all(r['passed'] for r in e['runs']) and len(e['runs'])==2
            b.record_local(cid,True,'V10.55/V12.39正常建立四台热泵及第一外机化霜；合法室温/再热配置分别令总目标0和4。'+('实际阶段8各观察3秒，两台Comp软件输出保持1。' if cid.endswith('018') else '实际恢复阶段7两轮各连续观察至少2.5秒，两台Comp软件输出均0，随后生命周期正常归0。')+'两轮均只读330普通CompControl命令，第一外机在该阶段未被普通加减载改写；命令布局从对应AXF调试信息解析。仅BENCH5秒恢复窗口及软件反馈，不证明正式60秒/端子。未写生命周期、需求、反馈、输出或计时。',e)
        data=json.loads(RESULTS.read_text('utf8'))
        for cid in ('T10-018','T10-019'):data[cid]['inputs']='Normal room calibration/reheat configuration and legacy HMI defrost command inputs; all commands/lifecycle/output/timers read-only'
        dump(RESULTS,data)
    except BaseException:b.log['error']=traceback.format_exc();b.save();raise
    finally:
        if ss:ss.close()
        b.finish()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    path=D/('recovery_allocation_controller_'+time.strftime('%H%M%S')+'.json');q=dict(started=now(),status='waiting_without_hardware',dependency=str(a.after));dump(path,q)
    try:
        while True:
            paused();prior=json.loads(a.after.read_text('utf8'))
            if prior.get('finished'):break
            time.sleep(3)
        assert prior.get('status')=='completed',prior
        restored_latest();q['status']='running';dump(path,q);run();restored_latest();q['checks']=[]
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8');q['checks'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(path,q);assert proc.returncode==0
        q['status']='completed'
    except BaseException:q.update(status='stopped_on_error',error=traceback.format_exc());raise
    finally:q['finished']=now();dump(path,q)
