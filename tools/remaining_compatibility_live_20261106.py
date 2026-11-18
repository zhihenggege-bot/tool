"""Board compatibility checks through normal parameters, not fault RAM writes.

DI polarity exercises the real digital filter and latches. Electrical contact
edges, terminal voltages, and HMI option presentation remain outside this run.
"""
from remaining_pid_live_20261106 import *


def fan_enums():
    b=HeatBench('fan_enumerations')
    try:
        for cid,reg,values in (('T07-014',330,(0,1,2)),('T07-015',331,(0,1))):
            entry=dict(passed=False,runs=[],hmi_tested=False)
            b.log['cases'][cid]=entry
            for value in values:
                b.setup(2)
                # [134] is supply manual AO; [131] is return manual AO.
                b.config({329:2,330:0,331:0,131:37,134:50,295:0,311:0,reg:value})
                b.start()
                b.wait(cid+' selected fans established', lambda s:
                    s['do'][3]==1 and s['ao'][7]==500 and
                    (s['do'][6]==int(value!=0) and s['ao'][4]==(370 if value==2 else 0)
                     if reg==330 else s['do'][8]==int(value==1) and s['ao'][4]==0), 40)
                rows=[];began=time.monotonic()
                while time.monotonic()-began<4:
                    s=b.snapshot(cid);rows.append(s)
                    assert s['state'][9]==2 and not any(s['faults']),s
                    assert s['do'][3]==1 and s['ao'][7]==500,s
                    if reg==330:
                        assert s['do'][6]==int(value!=0) and s['ao'][4]==(370 if value==2 else 0),s
                    else:
                        assert s['do'][8]==int(value==1) and s['ao'][4]==0,s
                    assert all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
                    time.sleep(.2)
                entry['runs'].append(dict(value=value,readback=b.rd(reg)[0],samples=rows))
                b.save();b.stop()
            entry['passed']=True
            b.record_local(cid,True,
                ('回风配置0/1/2逐档正常启动：无时DO/AO均0，开关时DO=1/AO=0，手动AO时DO=1且DA4=370；' if reg==330 else
                 '排风配置0/1逐档正常启动：Y10软件接点分别0/1，无新增排风AO；')+
                '送风DA7=500并带DO许可，各档观察4s；MCGS/Python界面呈现、非法枚举和端子未据此验收。',entry)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish()
        print('FAN ENUMS RESTORED',b.log.get('restored'),b.path,flush=True)


def extra_di(serial_only=False):
    b=HeatBench('compatibility_extra_di')
    ss=None
    try:
        if not serial_only:
            ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            ss.open();t=ss.target
        definitions=(('T05-037',394,'X_12',958),('T05-038',393,'X_11',956),
                     ('T05-039',395,'X_13',605),('T05-040',392,'X_10',910))
        def sample(label):
            s=b.snapshot(label);s.update(t=time.monotonic(),return_latch=b.rd(958)[0],
                exhaust_latch=b.rd(956)[0],humidifier_latch=b.rd(910)[0])
            return s
        def wait(label,predicate,seconds):
            rows=[];began=time.monotonic()
            while True:
                s=sample(label);rows.append(s)
                if predicate(s):return s,rows
                assert time.monotonic()-began<seconds,(label,s)
                time.sleep(.1)
        for cid,reg,raw,flag in definitions:
            b.setup(1)
            b.config({128:2,127:0,332:0,333:1,334:1,125:1,126:1,248:1,
                160:250,161:250,347:100,348:1,349:0,353:100,354:1,355:0,
                374:1,375:100,376:40,346:0,329:2,330:2,331:1,134:37,295:0,311:0})
            b.temperature(0,220);ai_exact(b,300);b.reset_faults();b.start()
            def established(s):
                return s['state'][9]==2 and all(s['do'][i] for i in (3,6,8)) and all(s['ao'][i]>0 for i in (0,1,2))
            before,rows=wait(cid+' establish',established,35)
            entry=dict(passed=False,before=before,establish_samples=rows,
                stimulus='正常DI极性模拟；未写故障、输出、需求、PID及计时RAM',terminal_tested=False)
            b.log['cases'][cid]=entry;b.save()
            original=b.rd(reg)[0]
            if serial_only:
                input_register={'X_12':1360,'X_11':1359,'X_13':1361,'X_10':1358}[raw]
                assert b.rd(input_register)[0]==0,(cid,'baseline DI display is not healthy')
                entry['serial_input_before']=dict(register=input_register,value=0)
            else:
                assert t.read8(b.sy[raw][0])==0,(cid,'baseline raw DI is not healthy')
            began=time.monotonic();b.wr(reg,1-original)
            if cid=='T05-040':
                tripped,trace=wait(cid+' humidifier off only',lambda s:b.rd(flag)[0]==1 and s['ao'][2]==0 and s['do'][11]==0,8)
                assert tripped['state'][9]==2 and all(tripped['do'][i] for i in (3,6,8)),tripped
                assert tripped['ao'][0]>0 and tripped['ao'][1]>0,tripped
            else:
                tripped,trace=wait(cid+' whole unit stop',lambda s:b.rd(flag)[0]==1 and s['state'][9]==0 and loads_off(s),8)
            elapsed=tripped['t']-began
            assert 2.5<=elapsed<=4.2,elapsed
            entry.update(trip=tripped,trip_samples=trace,reaction_observed_s=elapsed)
            b.wr(reg,original);time.sleep(.5)
            entry['signal_restored_without_reset']=sample(cid+' still latched')
            assert b.rd(flag)[0]==1,(cid,'latch cleared without reset')
            b.reset_faults()
            if cid!='T05-040':b.wr(398,0);time.sleep(.15);b.start()
            entry['recovered'],entry['recovery_samples']=wait(cid+' reset recovery',lambda s:established(s) and b.rd(flag)[0]==0,40)
            entry['passed']=True
            b.record_local(cid,True,f'制热时主热、预热、加湿AO及送/回/排风均先建立；{raw}极性模拟后约{elapsed:.3f}s动作；'+
                ('加湿软件AO/DO清零，热量与风机保留；' if cid=='T05-040' else '停整机、负载软件输出清零；')+
                '输入恢复后仍锁存，524复位后恢复。属工程兼容回归，实际接点及端子未测。',entry)
            b.stop()
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        if ss:ss.close()
        b.finish()
        print('EXTRA DI RESTORED',b.log.get('restored'),b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['fan-enums','extra-di'])
    action=p.parse_args().action
    (fan_enums if action=='fan-enums' else extra_di)()
