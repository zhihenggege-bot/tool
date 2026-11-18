"""Normal-protocol boundary rechecks and loaded preheat-fault verification."""
import json
import time
import traceback
from remaining571_common_20261105 import Bench, now
from run_indoor_bench_20261105 import result


def main(post_min=False):
    b = Bench('529_boundaries_x07')
    def record(cid, status, actual, entry, limits='BENCH软件回读；工程映射/DI极性模拟，非真实信号源和物理端子；正式版待测'):
        b.log['cases'][cid] = entry
        b.save()
        result(cid,status,actual,b.path,limits,'公开参数/工程量映射/DI极性；没有RAM注入或输出强制')
    try:
        for mode,cid in (() if post_min else ((2,'T07-005'),(3,'T07-006'))):
            b.setup(2);b.config({329:mode,330:0,336:2})
            if mode==3:b.ai(3,100,20)
            b.wr(398,1);time.sleep(6);rows=b.observe(cid,3)
            assert all(s['conflict'][0]&4 and s['do'][3]==0 and s['ao'][7]==0 for s in rows),rows[-1]
            record(cid,'部分通过',f'送风模式{mode}与送风阀AO冲突：940含0x04、Y03及DA7均0；原脚本误查0x01，已纠正后板上重测。',{'samples':rows})
            b.stop()
        for basis,cid in (() if post_min else ((0,'T08-010'),(1,'T08-011'))):
            b.setup(2);b.config({329:3,133:basis,339:60,340:60,341:30,342:90,
                290:1,291:10,343:0 if basis==0 else 720,344:100,345:0 if basis==1 else 100,
                294:70,310:700,295:0,311:0})
            b.ai(3,100,20);b.start();rows=b.observe(cid+' zero new target',3)
            targets=[s['diag'][28] for s in rows]
            status='部分通过' if all(t==0 for t in targets) else '失败'
            record(cid,status,f'新设定=0；旧目标294=70/310=700；实际目标900序列{targets}，AO序列{[s["ao"][7] for s in rows]}。'+('零设定未被替代。' if status!='失败' else '零设定被旧目标静默替代，规格允许0，需修正。'),{'samples':rows})
            b.stop()
        b.setup(2);b.config({329:3,133:1,339:60,341:90,342:30,345:100,290:1});b.ai(3,100,20)
        b.start();rows=b.observe('min>max',4)
        consistent=all(s['ao'][7]==900 for s in rows)
        record('T08-013','部分通过' if consistent else '失败',f'min=9V/max=3V，风机需求926={[s["diag"][54] for s in rows]}，最终DA7={[s["ao"][7] for s in rows]}。控制器将有效max钳至min；最终写入层若仍按原max限幅会与需求不一致，需要统一边界处理。',{'samples':rows},
            '规格未规定非法倒置参数必须停机；本例仅确认现有固定边界处理，不等于证明9V适合所有风机；界面拒绝/提示待验。')
        b.stop()
        allmix=[]
        for fresh,basis in ((0,0),(1,2),(2,0),(2,2),(2,1)):
            b.setup(2);b.config({335:fresh,377:basis,381:1,380:50,378:10,379:1000})
            if basis==0:b.ai(0,10)
            if basis==1:
                b.ai(1,500);b.ai(2,1000);b.ai(4,500)
            b.start();rows=b.observe(f'mix fresh{fresh} basis{basis}',2)
            valid=fresh==2 and basis==1
            assert all(s['ao'][3]+s['ao'][5]==1000 if valid else s['ao'][5]==0 for s in rows),rows[-1]
            allmix.append({'fresh':fresh,'basis':basis,'valid':valid,'samples':rows})
            b.stop()
        record('T07-009','部分通过','混风阀5组组合板上复核：无新风、开关新风、AO房压及AO手动均抑制DA5；仅AO+CO2焓差时互补和1000。原脚本错误要求排风阀专用0x20诊断，已纠正判据。',{'combinations':allmix},
            '正常协议及软件输出；真实Python/MCGS页面拒绝/提示与端子未验。')
        for humid,cid in ((1,'T03-007'),(2,'T03-008')):
            b.setup(1,thermal=True)
            b.config({333:1,374:0,357:100,358:0,334:humid,168:1,169:1,
                335:1,336:1,337:1,338:1,329:2})
            b.ntc(2,20);b.reset_faults();b.start()
            def established(s):return s['state'][9]==2 and s['ao'][0]>0 and s['ao'][1]>0 and (s['ao'][2]>0 if humid==1 else s['do'][11]==1)
            entry={'started':now(),'humidifier':humid}
            entry['before']=b.wait(cid+' main preheat humid established',established,30)
            b.wr(391,1-b.polarities[391]);short=b.observe(cid+' short X07',2)
            assert all(s['ao'][1]>0 for s in short)
            b.wr(391,b.polarities[391]);time.sleep(3.5)
            entry['short_input']=short
            entry['before_sustained']=b.wait(cid+' short pulse recovered',established,15)
            b.wr(391,1-b.polarities[391])
            entry['fault']=b.wait(cid+' X07 cuts loaded preheat',lambda s:b.rd(968)[0]==1 and s['ao'][1]==0 and s['ao'][2]==0 and s['do'][11]==0,12,True)
            def protected(s):return s['ao'][1]==0 and s['ao'][2]==0 and s['do'][11]==0 and s['ao'][0]>0 and all(s['do'][i]==1 for i in (3,6,8))
            entry['fault_hold']=b.observe(cid+' fault held',3)
            assert all(protected(s) for s in entry['fault_hold'])
            b.reset_faults();entry['reset_active']=b.observe(cid+' reset while X07 active',2)
            assert all(protected(s) for s in entry['reset_active'])
            b.wr(391,b.polarities[391]);entry['released_no_reset']=b.observe(cid+' X07 removed no reset',5)
            assert all(protected(s) for s in entry['released_no_reset'])
            b.reset_faults();entry['recovered']=b.wait(cid+' X07 reset restores loaded preheat',established,30)
            entry['passed']=True
            record(cid,'部分通过',f'预热AO已非0后模拟X07：短脉冲2秒未误切；持续故障关闭预热及加湿{humid}，主热和送/回/排风保留；故障仍在复位不恢复，去掉输入未复位仍锁存，524复位恢复。',entry)
            b.stop()
        b.log['passed']=True
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    print('COMPLETE',b.path,flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--post-min',action='store_true')
    main(p.parse_args().post_min)
