"""V10.52 normal-protocol verification of repaired automatic fan boundaries."""
import time,traceback
from remaining571_common_20261105 import Bench
from run_indoor_bench_20261105 import result

def main():
    b=Bench('529_fan_boundary_fixed')
    try:
        for basis,cid in ((0,'T08-010'),(1,'T08-011')):
            b.setup(2);b.config({329:3,133:basis,339:60,341:30,342:90,290:1,291:10,
                343:0 if basis==0 else 720,344:100,345:0 if basis==1 else 100,294:70,310:700,295:0,311:0})
            b.ai(3,100,20);b.start()
            b.wait(cid+' target zero',lambda s:b.rd(900)[0]==0,5)
            rows=b.observe(cid,4)
            assert all(s['diag'][28]==0 and 300<=s['ao'][7]<=900 for s in rows),rows[-1]
            result(cid,'部分通过',f'V10.52新设定0、旧目标294=70/310=700；反馈目标900连续为0，未回退旧目标；AO序列{[s["ao"][7] for s in rows]}。',b.path,
                '公开工程量映射及软件回读；真实信号源和端子待测；其余配置批末恢复。','正常参数输入，不写输出/目标/需求RAM')
            b.log['cases'][cid]={'samples':rows,'passed':True};b.save();b.stop()
        b.setup(2);b.config({329:3,133:1,339:60,341:90,342:30,345:100,290:1});b.ai(3,100,20)
        b.start();rows=b.observe('consistent inverted range',4)
        assert all(s['ao'][7]==900 and s['diag'][54]==900 for s in rows)
        b.log['cases']['T08-013']={'samples':rows,'passed':True};b.save()
        result('T08-013','部分通过','V10.52 min=90/max=30：需求926及最终DA7均900，连续4秒一致；与控制器既有“有效max钳至min”策略一致，消除原需求900而输出300差异。',b.path,
            '非法倒置参数的固定边界处理；页面提示与实际端子待验；未修改手动AO。','公开参数341/342输入，未写需求或输出')
        b.stop();b.wr(329,2)
        manual=[]
        for volt in (0,50,100):
            b.wr(134,volt);b.start();s=b.sample('manual regression')
            assert s['ao'][7]==volt*10 and s['do'][3]==1 and s['ao'][4]==500
            manual.append(s);b.stop()
        b.log['manual_regression']=manual;b.log['passed']=True
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    print('FAN BOUNDARY BOARD COMPLETE',b.path,flush=True)
if __name__=='__main__':main()
