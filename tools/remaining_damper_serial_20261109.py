"""Normal configuration stimulus; no RAM writes or electrical-terminal claim."""
from remaining_serial_only_live_20261106 import *


def exact(b, channel, value, display):
    center=value
    for _ in range(5):
        b.ai(channel,center)
        actual=signed16(b.rd(display)[0])
        b.log.setdefault('input_precision',[]).append(dict(channel=channel,wanted=value,actual=actual))
        if actual==value:return
        center+=value-actual
    raise AssertionError(('engineering input cannot reach exact value',channel,value,actual))


def main():
    b=SerialHeatBench('damper_pressure_enthalpy_20261109')
    b.log['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    b.log['scope']='Observed software behavior; numeric room-pressure/CO2 gains and enthalpy limiting are implementation regression, not numeric requirements stated by indoor specification.'
    report=R/'新风阀房压_CO2焓差_串口复测_20261109.md'
    summary=[]
    try:
        for mode in (0,1,2):
            b.setup(mode)
            b.config({329:2,330:0,331:1,335:2,377:0,378:50,381:0,338:0,
                      128:0,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
                      245:1,247:0,346:0})
            b.temperature(0,250);b.temperature(2,250)
            exact(b,0,50,902)
            b.reset_faults();b.start()
            pressure=[]
            for value in (0,1,49,50,51,99,100,99,51,50,49,1,0):
                exact(b,0,value,902)
                expected=max(0,min(1000,500+(50-value)*10))
                b.wait('room pressure settled',lambda s:s['ao'][3]==expected,8)
                rows=[]
                for _ in range(3):
                    s=b.snapshot('pressure stable')
                    assert not any(s['faults']) and s['ao'][3]==expected,s
                    assert s['ao'][5]==0 and s['ao'][6]==0,s
                    rows.append(s);time.sleep(.15)
                pressure.append(dict(input=value,expected=expected,samples=rows))
                print('PRESSURE',mode,value,expected,flush=True)
            summary.append(dict(mode=mode,pressure_points=len(pressure)))
            b.log.setdefault('pressure_runs',[]).append(dict(mode=mode,points=pressure));b.save()
            b.config({377:1,379:1000,381:1,338:2})
            exact(b,1,500,501)
            enthalpy=[]
            for relation,humidity in (('fresh_lower',200),('equal',500),('fresh_higher',800)):
                exact(b,4,humidity,519)
                if relation=='equal':
                    aligned=False
                    for attempt in range(8):
                        b.temperature(0,250);b.temperature(2,250)
                        temps=b.rd(511,2)
                        if temps[0]==temps[1]:aligned=True;break
                    if not aligned:
                        b.log.setdefault('skipped_equal_enthalpy',[]).append(dict(mode=mode,temperatures=temps,reason='Cannot establish exact equal-temperature input'))
                        continue
                for co2 in (0,500,999,1000,1001,1500,2000):
                    exact(b,2,co2,903)
                    temps=b.rd(511,2)
                    if relation=='equal' and temps[0]!=temps[1]:
                        b.log.setdefault('skipped_equal_enthalpy',[]).append(dict(mode=mode,co2=co2,temperatures=temps,reason='Equal-temperature stimulus drifted before sample'))
                        continue
                    demand=500+int((co2-1000)/2)
                    bad=(mode==0 and relation=='fresh_higher') or (mode==1 and relation=='fresh_lower')
                    expected=max(0,min(1000,min(demand,500) if bad else demand))
                    b.wait('CO2 enthalpy settled',lambda s:s['ao'][3]==expected and
                           s['ao'][3]+s['ao'][5]==1000 and s['ao'][6]==s['ao'][3],8)
                    rows=[]
                    for _ in range(3):
                        temps_before=b.rd(511,2)
                        if relation=='equal' and temps_before[0]!=temps_before[1]:
                            b.log.setdefault('skipped_equal_enthalpy',[]).append(dict(mode=mode,co2=co2,temperatures=temps_before,reason='Equal-temperature stimulus drifted; no equality acceptance'))
                            break
                        s=b.snapshot('CO2 enthalpy stable')
                        assert not any(s['faults']),s
                        assert s['ao'][3]==expected and s['ao'][5]==1000-expected and s['ao'][6]==expected,s
                        assert all(abs(v-250)<=3 for v in temps_before),temps_before
                        s['room_fresh_temperatures']=temps_before
                        rows.append(s);time.sleep(.15)
                    if len(rows)!=3:continue
                    enthalpy.append(dict(relation=relation,co2=co2,room_humidity=500,
                                          fresh_humidity=humidity,expected=expected,samples=rows))
                    b.log['enthalpy_in_progress']=enthalpy;b.save()
                    print('ENTHALPY',mode,relation,co2,expected,flush=True)
            b.log.setdefault('enthalpy_runs',[]).append(dict(mode=mode,points=enthalpy));b.save()
            summary[-1]['enthalpy_points']=len(enthalpy)
            b.stop()
        for cid,key,label in (('T07-028','pressure_runs','房间压差'),('T07-029','enthalpy_runs','CO2与焓差')):
            e=dict(passed=True,runs=b.log[key],scope=b.log['scope'])
            b.record_local(cid,True,f'{label}三模式已采集组合软件复核通过；正常工程量映射刺激，实际回读输入；房压升降方向/限幅、新回风低/高焓差，CO2 0/500/999/1000/1001/1500/2000；新风/混风互补及排风跟随。等焓输入不能稳定建立时跳过并保留日志，跳过数={len(b.log.get("skipped_equal_enthalpy",[]))}。数值增益为当前实现回归，规格未给出的增益不判定为规格已认证；物理信号/端子、异常输入和HMI待验。',e)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish()
        b.log['full_configuration_after']={}
        c=runtime.client()
        try:
            for a,n in ((0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2)):
                b.log['full_configuration_after'].update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
            b.log['full_configuration_mismatch']={k:[v,b.log['full_configuration_after'][k]] for k,v in b.full_before.items()
                if k not in ('167','373') and v!=b.log['full_configuration_after'][k]}
            b.log['independent_final']=runtime.snap(c)
            assert not b.log['full_configuration_mismatch'],b.log['full_configuration_mismatch']
            assert loads_off(b.log['independent_final'])
        finally:c.close();b.save()
        lines=['# 新风阀房压、CO2与焓差串口复测（2026-11-09）','',
            '330 V10.53 BENCH / 316 V12.39 BENCH；330调试口Get IDCODE错误，V10.54尚未烧录。',
            '正常参数/工程量映射模拟输入，软件AO回读；未测物理端子和真实风道闭环。房压/CO2数值增益及焓差限幅属于现有实现回归，规格未明确的数值不据此认证。','',
            '|模式|房压双向采样点|CO2×焓差组合|','|---|---:|---:|']
        for row in summary:lines.append(f"|{row['mode']}|{row['pressure_points']}|{row.get('enthalpy_points',0)}|")
        lines+=['',f"配置恢复：{b.log.get('restored')}；全量配置差异：{b.log.get('full_configuration_mismatch')}。",
                f"等焓输入未稳定而跳过的组：{b.log.get('skipped_equal_enthalpy',[])}。",
                '首轮因NTC读数未精确等于25.0℃而中断，属采样前提问题；原始失败及恢复保存在同目录084432日志，未改固件。',
                f"错误（空表示无）：{b.log.get('error','无')}。",f'\n[原始证据]({b.path.relative_to(R).as_posix()})']
        report.write_text('\n'.join(lines)+'\n','utf8')
        print('DAMPER BATCH RESTORED',b.log.get('restored'),b.path,flush=True)


if __name__=='__main__':main()
