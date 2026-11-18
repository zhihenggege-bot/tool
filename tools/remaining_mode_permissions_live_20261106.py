"""Temperature/humidity mode permissions with normal input configuration."""
from remaining_pid_live_20261106 import *


def main():
    b=HeatBench('mode_temperature_humidity_permissions')
    try:
        for mode,cid in ((2,'T02-026'),(0,'T02-027'),(1,'T02-028')):
            b.setup(mode)
            b.config({128:2,127:1,129:1,332:1,333:1,334:1,248:1,
                160:250,161:250,162:500,120:20,361:200,412:1,
                347:100,348:1,349:0,350:10,351:1,352:0,
                353:10,354:1,355:0,374:1,375:100,376:40,
                329:2,330:0,331:0,346:0,315:0,320:0})
            b.temperature(0,250)
            ai_exact(b,500)
            b.start()
            entry=dict(passed=False,mode=mode,points=[],
                stimulus='合法室温NTC校准与AI1工程映射；未写需求、输出、PID或计时RAM',
                limits='软件模式许可；物理温湿度信号源、端子及正式时序未测')
            b.log['cases'][cid]=entry
            for humid_control in (0,1):
                b.config({125:humid_control,126:humid_control})
                for temp in (220,250,280):
                    b.temperature(0,temp)
                    for rh in (400,500,700):
                        ai_exact(b,rh)
                        point=dict(control=humid_control,requested_temperature=temp,requested_rh=rh,samples=[])
                        began=time.monotonic()
                        while time.monotonic()-began<10:
                            s=b.snapshot(cid)
                            s['temperature']=signed16(b.rd(511)[0]);s['humidity']=b.rd(501)[0]
                            s['thermal_diagnostics']=b.rd(890,3)
                            s['capacity_diagnostics']=b.rd(872,10)
                            point['samples'].append(s)
                            assert s['state'][9]==2 and not any(s['faults']),s
                            assert abs(s['temperature']-temp)<=1 and s['humidity']==rh,s
                            if mode==2:
                                assert all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
                                assert all(s['do'][i]==0 for i in (0,1,2,10,11,13,14,15)),s
                                assert all(v==0 for pair in s['outdoor_status'] for v in pair),s
                            if not humid_control:
                                assert s['ao'][2]==0 and s['do'][11]==0 and s['thermal_diagnostics'][2]==0,s
                                if mode==0:
                                    assert signed16(s['capacity_diagnostics'][5])==0,s
                            if mode==0: assert s['ao'][1]==0,s
                            if mode==1:
                                assert all(v==0 for pair in s['outdoor_status'] for v in pair),s
                            time.sleep(.25)
                        last=point['samples'][-1]
                        if mode!=2 and humid_control and rh==400:
                            assert last['ao'][2]>0,last
                        if mode!=2 and humid_control and rh==700:
                            assert last['ao'][2]==0,last
                        entry['points'].append(point)
                        b.save()
                        print('MODE PERMISSION',mode,humid_control,temp,rh,'AO',last['ao'],'passed',flush=True)
            assert len(entry['points'])==18
            entry['passed']=True
            b.record_local(cid,True,'室温22/25/28℃×湿度40/50/70%×恒温/恒温恒湿共18组合，每点真实观察10s；'
                '通风冷热湿负载关闭、恒温加湿关闭、恒湿低湿加湿建立及高湿关闭；制冷预热禁止、非热泵制热外机保持停止。'
                '零误差区保留PID现有需求，不误按“必须清零”判定；软件输入/输出证据。',entry)
            b.stop()
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish()
        print('MODE PERMISSIONS RESTORED',b.log.get('restored'),b.path,flush=True)


if __name__=='__main__':main()
