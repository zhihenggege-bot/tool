"""Unfinished indoor bridge/allocation checks using ordinary inputs only."""
from joint_priority_20261110 import *
import struct
from nonvent_recovery_allocation_20261109 import command_layout

def allocation():
    b=TodayBench('T10-018_T10-019_allocation')
    e=dict(started=now(),status='running',runs=[]);b.log['priority_case']=e;b.save();ss=None
    try:
        stride,offset=command_layout()
        # Exact source and DWARF declare int16_t CompControl[4], not uint32_t.
        e['command_layout']=dict(stride=stride,offset=offset,word_bytes=2)
        for target,temp,reheat in ((0,280,0),(4,220,1)):
            b.prepare();b.config({127:reheat});b.temperature(0,temp)
            b.until('defrost active target'+str(target),lambda s:s['phase']==[8,8] and s['target_count']==target,30)
            ss=ConnectHelper.session_with_chosen_probe(blocking=False,unique_id=BOARDS[2][1],target_override=BOARDS[2][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            assert ss;ss.open();t=ss.target
            def sample(label):
                s=b.sample(label);s['ordinary_commands']=[list(struct.unpack('<2h',bytes(t.read_memory_block8(b.sy['UnitWriteStatus'][0]+m*stride+offset,4)))) for m in (1,2)];return s
            r=dict(target=target,active=[],recovery=[]);e['runs'].append(r)
            began=time.monotonic();commands=None
            while time.monotonic()-began<3:
                s=sample('active8 allocation');r['active'].append(s)
                assert s['phase']==[8,8] and s['target_count']==target and s['outdoor_comp']==[1,1],s
                if commands is None:commands=s['ordinary_commands'][0]
                assert s['ordinary_commands'][0]==commands,s
                time.sleep(.08)
            manual_defrost(b,False,session=ss);began=time.monotonic();first=None;last=None
            while True:
                s=sample('recovery7 allocation');r['recovery'].append(s)
                if s['phase']==[7,7]:
                    if first is None:first=s['monotonic']
                    last=s['monotonic'];assert s['target_count']==target and s['outdoor_comp']==[0,0] and s['ordinary_commands'][0]==commands,s
                if first is not None and s['phase']==[0,0]:break
                assert time.monotonic()-began<90,('recovery incomplete',s);time.sleep(.06)
            assert first is not None and last-first>=2.5,(first,last)
            r.update(recovery_observed_s=last-first,software_scope_passed=True);b.save();ss.close();ss=None;b.stop()
            print('ALLOCATION BOTH PHASES target',target,'software scope passed',flush=True)
        e['status']='软件子范围通过：目标0/4下阶段8和BENCH恢复7未被普通分配改写'
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        if ss:ss.close()
        try:b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

def refrigerant():
    b=TodayBench('T12-005_refrigerant_bridge');e=dict(started=now(),runs=[],status='running');b.log['priority_case']=e;b.save()
    try:
        b.attach_extra()
        assert loads_off(b.snapshot('stopped refrigerant bridge'))
        for value in (0,1,2,3):
            b.config({39:value});began=time.monotonic();r=dict(requested=value,samples=[]);e['runs'].append(r)
            while True:
                z=dict(at=now(),outdoor=[])
                for board,ss,sy in [(BOARDS[0],b.outss,b.outsy),b.extra[0]]:
                    t=ss.target;p=sy['Parameter'][0]
                    z['outdoor'].append(dict(board=board[0],refrigerant=t.read16(p+78),low_pressures=[t.read16(p+2*a) for a in (1444,1446)],evap=[signed16(t.read16(p+2*a)) for a in (1447,1448)],superheat=[signed16(t.read16(p+2*a)) for a in (1437,1438)]))
                z['indoor_mirrors']=[b.rd(1577,2),b.rd(1647,2)];r['samples'].append(z)
                if all(x['refrigerant']==value for x in z['outdoor']) and time.monotonic()-began>=5:break
                assert time.monotonic()-began<35,('refrigerant not propagated',z);time.sleep(.4)
            r['bridge_passed']=True;b.save();print('REFRIGERANT BRIDGE',value,z['outdoor'],flush=True)
        e['status']='桥接子范围通过；换算准确度、PID响应和实际制冷剂另验'
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

def da8():
    b=TodayBench('T06-024_DA8_manual_characterization')
    e=dict(started=now(),status='running',phases=[],scope='Characterize legacy manual AO route; independent medium-permission requirement remains unconfirmed')
    b.log['priority_case']=e;b.save()
    try:
        b.setup(0);b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,160:250,161:250,120:20,412:1,315:0,320:0,346:0,245:1,247:0,329:2,330:0,331:0})
        b.temperature(0,250);b.reset_faults();b.start()
        for value in (0,500,0):
            b.config({314:0,247:value});time.sleep(.6);r=dict(manual_request=value,samples=[]);e['phases'].append(r);began=time.monotonic()
            while time.monotonic()-began<4:
                s=b.snapshot('DA8 legacy manual path');s.update(select314=b.rd(314)[0],manual245_247=b.rd(245,3),da8_display=b.rd(925)[0]);r['samples'].append(s)
                assert not any(s['faults']) and s['state'][9]==2,s;time.sleep(.2)
            b.save()
        e['all_manual_steps_match']=all(all(s['ao'][8]==r['manual_request'] for s in r['samples']) for r in e['phases'])
        e['status']=('现象复现：旧手动参数247可令DA8输出500；独立介质许可口径待确认，暂不定固件缺陷' if e['all_manual_steps_match'] else '本轮未复现完整0/500/0轨迹；见逐段实际回读')
        print('DA8',e['status'],flush=True)
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('allocation','refrigerant','da8'));a=p.parse_args()
    {'allocation':allocation,'refrigerant':refrigerant,'da8':da8}[a.action]()
