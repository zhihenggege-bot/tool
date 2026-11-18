"""Additional serial-only boundary checks; ordinary parameter inputs only.

No debug port, demand/output/history writes, or out-of-range calibration.
Public diagnostics qualify permissions, not private PID fractional state.
"""
from remaining_serial_only_live_20261106 import SerialHeatBench, ai_exact, time, now, signed16, traceback


def ys_permissions():
    b=SerialHeatBench('ys_permissions')
    try:
        b.setup(0)
        b.config({128:0,127:1,129:0,332:1,333:0,334:1,125:1,126:0,248:1,
            168:0,160:250,161:250,162:500,361:200,120:20,315:0,320:0,
            347:1,348:1000,349:0,353:1,354:1000,355:0,
            412:3,416:11,417:37,418:9,346:0,245:1,247:0,
            329:2,330:0,331:0})
        b.temperature(0,250);ai_exact(b,601);b.start()

        def sample(label):
            d=b.rd(872,22)
            return dict(at=now(),t=time.monotonic(),diagnostics=d,ys=signed16(d[5]),
                error=signed16(d[2]),e1=signed16(d[3]),e2=signed16(d[4]),
                reheat=d[18],humid=d[20],rh=b.rd(501)[0],room=signed16(b.rd(511)[0]),
                sd=b.rd(162)[0],sdf=b.rd(361)[0],snapshot=b.snapshot(label))

        def check(cid,want,predicate,label):
            began=time.monotonic();rows=[];stable_since=None
            while True:
                s=sample(cid);rows.append(s)
                assert not any(s['snapshot']['faults']) and s['snapshot']['state'][9]==2,s
                if predicate(s) and s['ys']==want:
                    if stable_since is None:stable_since=time.monotonic()
                    if time.monotonic()-stable_since>=9:break
                else:stable_since=None
                assert time.monotonic()-began<30,(cid,'permission/input did not settle',s)
                time.sleep(.15)
            entry=dict(passed=True,rows=rows,expected_ys=want,
                public_diagnostics_only=True,private_pid_residual_verified=False,
                phase=label,continuous_match_seconds=time.monotonic()-stable_since)
            b.record_local(cid,True,label+f'；YS公开诊断={want}/10℃持续至少9s，T3/KP11/TI37/TD9；实际误差及两拍历史同步保留。只验许可及诊断，不据此签私有PID余数逐拍公式、端子或正式档。',entry)

        base=lambda s:s['rh']==601 and s['room']==250 and s['reheat']<1000 and s['humid']==0 and s['snapshot']['ao'][2]==0 and s['snapshot']['do'][11]==0
        check('T11-057',20,base,'恒湿、湿度60.1%、加湿关闭、再热未满载及温度在范围内全部前提建立')
        b.config({125:0})
        check('T11-058',0,base,'仅撤销恒湿要求，其余基准前提保留')
        b.config({125:1});b.temperature(0,261)
        check('T11-061',0,lambda s:s['room']==261 and s['rh']==601 and s['humid']==0 and s['reheat']<1000,'温度26.1℃超过WD25±WDF/2，其余许可保留')
        b.temperature(0,250);ai_exact(b,600)
        check('T11-062',0,lambda s:s['room']==250 and s['rh']==600 and s['humid']==0 and s['reheat']<1000,'湿度等于SD+SDF/2=60.0%，严格大于不成立')
        ai_exact(b,601)
        check('T11-063',20,base,'湿度恢复60.1%，严格大于成立，YS恢复2℃')

        # Obtain genuine humidifier output, then restore SD50 with a low gain.
        # Every accepted sample must retain high RH and a real open humidifier.
        b.config({162:700,353:100,354:1})
        b.wait('YS humidifier real output established',lambda s:b.rd(892)[0]==1000 and s['ao'][2]==1000,25)
        b.config({353:1,354:1000,162:500})
        check('T11-059',0,lambda s:s['room']==250 and s['rh']==601 and s['sd']==500 and s['sdf']==200 and s['humid']>0 and s['snapshot']['ao'][2]>0 and s['reheat']<1000,'正常PID先建立加湿，恢复SD50后加湿仍实际输出，温度与高湿等其它前提满足')

        # Reset humidifier via its normal equipment selector and establish
        # full reheat using legal temperature input. Deadband then retains it.
        b.config({334:0});b.wait('YS humidifier closed',lambda s:b.rd(892)[0]==0 and s['ao'][2]==0,8)
        b.config({347:100,348:1});b.temperature(0,240)
        b.wait('YS reheat real full demand',lambda s:b.rd(890)[0]==1000 and s['ao'][9]==1000,25)
        b.config({347:1,348:1000});b.temperature(0,250)
        check('T11-060',0,lambda s:s['room']==250 and s['rh']==601 and s['reheat']==1000 and s['snapshot']['ao'][9]==1000 and s['humid']==0 and s['snapshot']['ao'][2]==0,'正常PID建立独立再热满载，回到温度死区保持1000；其余YS前提满足')
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish();print('SERIAL YS RESTORED',b.log.get('restored'),flush=True)


def heat_upper():
    b=SerialHeatBench('heat_upper_boundaries')
    try:
        by_case={cid:dict(passed=False,runs=[]) for cid in ('T11-067','T11-068','T11-069')}
        b.log['cases']=by_case
        for owner in ('main','independent_reheat'):
            b.setup(1 if owner=='main' else 0)
            b.config({128:2 if owner=='main' else 0,127:int(owner!='main'),129:0,332:int(owner!='main'),
                333:0,334:0,125:0,126:0,248:0,315:0,320:0,160:250,161:250,
                347:100,348:1,349:0,412:1,120:20,346:0,245:1,247:0,
                329:2,330:0,331:0})
            b.temperature(0,220);b.start();channel=0 if owner=='main' else 9
            initial=b.wait(owner+' full heat established',lambda s:b.rd(890)[0]==1000 and s['ao'][channel]==1000,30)
            b.config({347:1,348:1000})
            for cid,temp in (('T11-067',312),('T11-068',313),('T11-069',320)):
                b.temperature(0,temp)
                began=time.monotonic();rows=[]
                while time.monotonic()-began<5:
                    s=b.sample_heat(cid);s.update(room=signed16(b.rd(511)[0]),snapshot=b.snapshot(cid))
                    if s['room']!=temp:time.sleep(.08);continue
                    assert not any(s['snapshot']['faults']),s
                    assert (s['heat']>0 and s['ao'][channel]>0) if temp==312 else (s['heat']==0 and s['ao'][channel]==0),s
                    assert all(s['ao'][i]==0 for i in {0,9}-{channel}),s
                    rows.append(s);time.sleep(.15)
                assert len(rows)>=5,(cid,'insufficient exact-temperature samples')
                by_case[cid]['runs'].append(dict(owner=owner,channel=channel,temperature=temp,initial=initial,rows=rows))
                b.save()
            b.stop()
        for cid,e in by_case.items():
            e['passed']=len(e['runs'])==2
            temp=e['runs'][0]['temperature']/10
            b.record_local(cid,e['passed'],f'WD25℃，主热DA0及独立再热DA9分别先正常PID升至1000，再合法校准到室温{temp:.1f}℃；'+('31.2℃仍由PID保持非零热量，未因严格高温边界强关。' if temp==31.2 else '高于31.25℃，需求及对应AO强制清零。')+'每路精确温度观察5s；最小输出设0。NTC2现26.4℃，合法±10℃不能构造−1℃冬季条件，该子项跳过；0.1℃分辨率不能测31.25℃等号，端子/正式档未验。',e)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish();print('SERIAL UPPER HEAT RESTORED',b.log.get('restored'),flush=True)
