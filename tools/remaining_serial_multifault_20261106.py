"""Two remaining multi-fault cases, through legal serial DI settings only.

No fault/output/history RAM writes and no debug probe. Scope is software
priority, latching and restoration, not electrical contacts or terminals.
"""
from remaining_serial_only_live_20261106 import SerialHeatBench,ai_exact,time,now,traceback,loads_off


def main(with_humidity=False):
    b=SerialHeatBench('multifault_priorities')
    try:
        for cid in ('T05-041','T05-043'):
            e=dict(passed=False,phases=[],stimulus='Normal DI polarity configuration; no fault/output/timer RAM writes',
                scope='Software priority and reset/recovery; physical contacts/terminals/PRODUCTION pending',
                humidity_output_qualified=with_humidity)
            b.log['cases'][cid]=e;b.save()
            try:
                b.setup(1)
                b.config({128:2,127:0,332:0,333:1,334:int(with_humidity),125:int(with_humidity),126:int(with_humidity),248:int(with_humidity),
                    160:250,161:250,347:100,348:1,349:0,350:100,351:1,352:0,
                    353:100,354:1,355:0,374:1,375:100,376:40,346:0,
                    329:2,330:0,331:0,245:1,247:0})
                b.temperature(0,220)
                if with_humidity:ai_exact(b,300)
                b.reset_faults();b.start()

                def sample(label):
                    s=b.snapshot(label)
                    s.update(t=time.monotonic(),fire_valve_latch=b.rd(605)[0],filter_alarm=b.rd(909)[0],
                        heat_latch=b.rd(966)[0],heating_fault=b.rd(924)[0],
                        inputs=b.rd(1350,7))
                    return s

                def established(s):
                    return s['state'][9]==2 and s['do'][3]==1 and all(s['ao'][i]>0 for i in ((0,1,2) if with_humidity else (0,1)))

                def wait(label,predicate,seconds):
                    began=time.monotonic();rows=[]
                    while True:
                        s=sample(label);rows.append(s)
                        if predicate(s):
                            e['phases'].append(dict(label=label,elapsed_s=time.monotonic()-began,samples=rows));b.save()
                            print('MULTIFAULT PHASE',cid,label,round(time.monotonic()-began,3),flush=True)
                            return s
                        assert time.monotonic()-began<seconds,(cid,label,s)
                        time.sleep(.15)

                def hold(label,predicate,seconds):
                    began=time.monotonic();rows=[]
                    while time.monotonic()-began<seconds:
                        s=sample(label);rows.append(s);assert predicate(s),(cid,label,s)
                        time.sleep(.15)
                    e['phases'].append(dict(label=label,elapsed_s=time.monotonic()-began,samples=rows));b.save()
                    print('MULTIFAULT HOLD',cid,label,round(time.monotonic()-began,3),flush=True)

                def stimulus(reg,bad):
                    original=b.polarities[reg]
                    b.config({reg:1-original if bad else original})

                initial=wait('all thermal outputs established',established,35)
                e['initial']=initial
                assert initial['inputs']==[0,0,1,0,0,0,0],('unhealthy baseline DI',initial['inputs'])

                if cid=='T05-041':
                    stimulus(389,True)
                    wait('filter alone alarms after real 15s',lambda s:s['filter_alarm']==1 and established(s),20)
                    hold('filter alone preserves all established loads',established,2)
                    stimulus(156,True)
                    wait('fire plus filter stop all loads',lambda s:s['fire_valve_latch']==1 and s['filter_alarm']==1 and s['state'][9]==0 and loads_off(s),8)
                    stimulus(156,False)
                    wait('fire input recovered, latch remains',lambda s:s['inputs'][1]==0 and s['fire_valve_latch']==1,6)
                    b.reset_faults();b.wr(398,0);b.start()
                    wait('fire reset, filter input still active, loads may run',lambda s:established(s) and s['inputs'][5]==1 and s['fire_valve_latch']==0,35)
                    wait('active filter alarms again after reset without stopping',lambda s:s['filter_alarm']==1 and established(s),20)
                    stimulus(156,True)
                    wait('both faults reapplied',lambda s:s['fire_valve_latch']==1 and s['filter_alarm']==1 and s['state'][9]==0 and loads_off(s),8)
                    stimulus(389,False)
                    wait('only filter input recovered',lambda s:s['inputs'][5]==0 and s['inputs'][1]==1,6)
                    b.reset_faults()
                    wait('filter reset cannot clear active fire stop',lambda s:s['filter_alarm']==0 and s['fire_valve_latch']==1 and s['state'][9]==0 and loads_off(s),6)
                    hold('active fire remains dominant after filter reset',lambda s:s['fire_valve_latch']==1 and s['state'][9]==0 and loads_off(s),5)
                    stimulus(156,False)
                    wait('both inputs healthy, fire still latched',lambda s:s['inputs'][1]==0 and s['inputs'][5]==0 and s['fire_valve_latch']==1,6)
                    b.reset_faults();b.wr(398,0);b.start()
                    wait('both cleared and reset, all loads recover',lambda s:established(s) and s['fire_valve_latch']==0 and s['filter_alarm']==0,35)
                    actual='正常制热主热/预热'+('/加湿' if with_humidity else '')+'先建立；滤网只报警；叠加消防后停整机。只清消防并复位，滤网仍有效但负载可恢复、15秒后重新报警；只清滤网并复位，消防仍有效且持续停机；两输入都恢复并复位后负载恢复。'
                else:
                    stimulus(390,True)
                    wait('heat fault closes heat and humidity only',lambda s:s['heat_latch']==1 and s['ao'][0]==0 and s['ao'][2]==0 and s['state'][9]==2 and s['ao'][1]>0 and s['do'][3]==1,8)
                    stimulus(157,True)
                    wait('remote open while heat fault retained, orderly stop',lambda s:s['inputs'][2]==0 and s['heat_latch']==1 and s['state'][9]==0 and loads_off(s),160)
                    stimulus(390,False)
                    wait('heat input restored while remote stays open',lambda s:s['inputs'][6]==0 and s['inputs'][2]==0,6)
                    b.reset_faults()
                    wait('heat reset cannot bypass remote stop',lambda s:s['heat_latch']==0 and s['state'][9]==0 and loads_off(s),6)
                    hold('remote stop dominates heat reset',lambda s:s['inputs'][2]==0 and s['state'][9]==0 and loads_off(s),5)
                    stimulus(390,True)
                    wait('heat fault active again while remote open',lambda s:s['heat_latch']==1 and s['inputs'][6]==1,8)
                    stimulus(157,False)
                    wait('remote restores fan while heat fault still active',lambda s:s['inputs'][2]==1 and s['heat_latch']==1 and s['state'][9]==2 and s['do'][3]==1 and s['ao'][0]==0 and s['ao'][2]==0,50)
                    b.reset_faults()
                    hold('reset during active heat fault cannot reenable heat or humidity',lambda s:s['heat_latch']==1 and s['state'][9]==2 and s['do'][3]==1 and s['ao'][0]==0 and s['ao'][2]==0,5)
                    stimulus(390,False)
                    wait('heat signal healthy but latch remains',lambda s:s['inputs'][6]==0 and s['heat_latch']==1,6)
                    b.reset_faults()
                    wait('all clear and reset restores thermal outputs',lambda s:established(s) and s['heat_latch']==0,35)
                    actual='正常制热主热/预热'+('/加湿' if with_humidity else '')+'先建立；电热故障切主热，加湿输出为0，远程断开后正常全停。只清电热并复位不能越过远程停机；远程恢复后风机自动重启，但仍有效的电热故障继续封锁主热，按复位也不能越过；排故并复位后热输出恢复。'
                if not with_humidity:actual+='本批因AI1输入无效，正常配置为无控湿/无加湿，未验证加湿从有输出到关闭及恢复，不据此签加湿联动。'
                e.update(passed=True,finished=now())
                b.record_local(cid,True,actual+'DI极性参数模拟及公开状态回读；物理接点/端子、正式档未验。',e)
            except Exception:
                e.update(error=traceback.format_exc(),finished=now());b.save()
                b.record_local(cid,False,e['error'].splitlines()[-1],e)
            finally:
                for reg,v in b.polarities.items():
                    if reg in b.touched:b.config({reg:v})
                time.sleep(3.5);b.reset_faults();b.stop()
    finally:
        b.finish();print('SERIAL MULTIFAULT RESTORED',b.log.get('restored'),b.path,flush=True)


if __name__=='__main__':main()
