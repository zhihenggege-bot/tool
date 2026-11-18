"""BENCH automatic fan software loop with explicitly simulated engineering feedback."""
import time, traceback
from run_indoor_bench_20261105 import ControlBench, result, now


def main():
    b = ControlBench('automatic_fan_simulated_feedback')

    def feedback(pressure, speed):
        a = 1265
        b.config({a:1,a+4:pressure,a+5:pressure,a+6:speed,a+7:speed,a+8:0})
        b.wait('mapped feedback',lambda s:b.rd(1125)[0]==pressure and b.rd(1126)[0]==speed,10)

    try:
        for basis, cid in [(1,'T08-005'),(0,'T08-006')]:
            entry={'started':now(),'basis':basis,'stimulus':'正常AI3工程量量程映射模拟反馈；保留ADC与故障滤波，非真实风压/风速信号'}
            b.log['cases'][cid]=entry
            try:
                b.baseline(2)
                b.config({329:3,330:2,331:1,131:40,133:basis,
                          339:60,340:60,341:30,342:90,
                          290:5,291:10,343:720,344:100,345:100,295:0,311:0})
                feedback(50,10)
                b.wr(398,1)
                first=b.wait(cid+' running',lambda s:s['state'][9]==2 and s['do'][3]==1,30)
                initial=first['ao'][7]
                high=b.wait(cid+' low feedback raises demand',lambda s:s['ao'][7]>initial,12)
                entry['initial_ao']=initial
                entry['raised_ao']=high['ao'][7]
                feedback(150,30)
                high_level=b.snapshot(cid+' high feedback beginning')['ao'][7]
                lowered=b.wait(cid+' high feedback reduces demand',lambda s:s['ao'][7]<high_level,12)
                entry['lowered_ao']=lowered['ao'][7]
                feedback(100,20)
                hold_ao=b.snapshot(cid+' target feedback beginning')['ao'][7]
                end=time.monotonic()+12
                entry['target_hold_samples']=[]
                while time.monotonic()<end:
                    s=b.snapshot(cid+' target hold')
                    entry['target_hold_samples'].append(s)
                    assert s['ao'][7]==hold_ao and 300<=s['ao'][7]<=900 and s['do'][3]==1, (cid,'hold/bounds/enable',s)
                    assert s['ao'][4]==400 and s['do'][6]==1,(cid,'manual return disturbed',s)
                    assert not any(s['faults']), (cid,'fault',s)
                    time.sleep(.3)
                b.stop()
                entry['software_checks_passed']=True
                entry['finished']=now()
                b.save()
                result(cid,'部分通过',f"通风自动送风：模拟反馈低→升{initial}至{entry['raised_ao']}，高→降至{entry['lowered_ao']}，目标反馈保持12s；DO运行许可与手动回风4V保持",b.path,
                       '只证明模拟反馈下的软件闭环；真实信号源、端子及负载闭环未测；最终恢复见证据',entry['stimulus'])
            except BaseException:
                entry['error']=traceback.format_exc()
                b.save()
                result(cid,'失败',entry['error'].splitlines()[-1],b.path,'保留原始样本；最终恢复见证据')
                raise
    finally:
        b.finish()


if __name__=='__main__':
    main()
