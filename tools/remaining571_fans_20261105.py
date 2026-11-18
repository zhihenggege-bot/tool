"""Remaining BENCH fan checks; software evidence, never terminal acceptance."""
import time, traceback
from remaining571_common_20261105 import Bench, case_error, now

def main():
    b=Bench('fans')
    try:
        for cid,fanmode,ret in [('T02-019',2,False),('T02-020',3,False),('T02-021',2,True)]:
            entry={'started':now(),'checks':[]};b.log['cases'][cid]=entry
            try:
                for emergency in (False,True):
                    b.setup(2)
                    b.config({329:fanmode,134:0 if not ret else 50,131:0 if ret else 50,
                              339:0,340:0,341:0,342:100,290:5,133:1,345:100})
                    if fanmode==3:b.ai(3,100,20)
                    b.start()
                    ch,di=(4,6) if ret else (7,3)
                    run=b.wait(cid+' zero speed enable',lambda s:s['ao'][ch]==0 and s['do'][di]==1,20)
                    entry['checks'].append({'phase':'established','emergency':emergency,'sample':run})
                    if emergency:
                        # X03 overcurrent; normal persisted DI polarity stimulation.
                        b.wr(158,1-b.polarities[158])
                        stopped=b.wait(cid+' emergency',lambda s:s['state'][9]==0 and s['do'][di]==0 and s['ao'][ch]==0,15,True)
                        b.wr(398,0);b.wr(158,b.polarities[158]);time.sleep(3.3);b.reset_faults()
                    else:stopped=b.stop()
                    assert stopped['do'][di]==0 and stopped['ao'][ch]==0
                    b.observe(cid+' no stale writer',3)
                    entry['checks'].append({'phase':'stopped','emergency':emergency,'sample':stopped})
                b.record(cid,'部分通过','零速AO时DO仍为1；正常停机和X03极性模拟急停均撤AO/DO，停后观察3秒无重置。',
                         '已实测软件链路；真实X03接点、端子电压/继电器测量待补',entry)
            except Exception as e:case_error(b,cid,e)
        for cid,cfg in [('T02-022',(1,1,1)),('T02-023',(1,0,0)),('T02-024',(2,0,0)),('T02-025',(3,2,1))]:
            try:
                b.setup(2);b.config(dict(zip((329,330,331),cfg)))
                if cfg[0]==3:b.config({339:60,341:30,342:90,133:1,345:100});b.ai(3,100,20)
                b.start();rows=b.observe(cid+' identity',5)
                for s in rows:
                    assert [s['do'][i] for i in (3,6,8)]==[1,int(cfg[1]!=0),cfg[2]],s
                    assert (s['ao'][7]>0)==(cfg[0]!=1),s
                    assert (s['ao'][4]>0)==(cfg[1]==2),s
                b.stop()
                b.record(cid,'部分通过',f'329/330/331={cfg}；软件Y03/Y06/Y10与DA7/DA4身份及停机清零吻合。',
                         '软件数组身份核验；逐路物理端子身份和不存在设备的精确延时待补',{'samples':rows})
            except Exception as e:case_error(b,cid,e)

        # Feedback through normal AI3 engineering ranges; no writes to DA/output.
        for mode,basis,cid in [(0,1,'T08-001'),(0,0,'T08-002'),(1,1,'T08-003'),(1,0,'T08-004')]:
            try:
                b.setup(mode);b.config({329:3,133:basis,339:60,340:60,341:30,342:90,290:5,291:10,
                                     343:720,344:100,345:100,295:0,311:0})
                b.ai(3,50,10);s=b.start();initial=s['ao'][7]
                raised=b.wait(cid+' low feedback',lambda s:s['ao'][7]>initial,13)
                b.ai(3,150,30);high=b.sample(cid+' high feedback start')['ao'][7]
                lowered=b.wait(cid+' high feedback',lambda s:s['ao'][7]<high,13)
                b.ai(3,100,20);time.sleep(.5);hold=b.sample(cid+' hold')['ao'][7]
                rows=b.observe(cid+' hold',11)
                assert all(s['ao'][7]==hold and 300<=s['ao'][7]<=900 and s['do'][3]==1 and s['do'][6]==1 and s['ao'][4]==500 for s in rows)
                b.record(cid,'部分通过',f'模式{mode}依据{basis}：低反馈升{initial}→{raised["ao"][7]}，高反馈降至{lowered["ao"][7]}；目标处11秒保持，回风手动5V不变。',
                         '工程量量程映射模拟反馈；真实信号源闭环/物理端子和精确周期/步长待补',{'initial':initial,'raised':raised,'lowered':lowered,'hold':rows})
            except Exception as e:case_error(b,cid,e)
        for cid,cfg in [('T08-009',{343:720,344:100}),('T08-010',{343:0,344:100}),
                        ('T08-011',{345:0,133:1}),('T08-012',{341:60,342:60}),
                        ('T08-013',{341:90,342:30}),('T08-014',{339:80,340:100,134:30,131:40})]:
            try:
                b.setup(2);b.config({329:3,133:0,339:60,340:60,341:30,342:90,290:1,291:10,343:720,344:100,345:100})
                b.config(cfg);b.ai(3,100,20);b.start();rows=b.observe(cid,4)
                extra=[]
                if cid=='T08-009':
                    for volume,area in ((1440,200),(720,200)):
                        b.config({343:volume,344:area});extra+=b.observe(cid+' ratio',4)
                    assert all(s['ao'][7]==rows[-1]['ao'][7] for s in extra[:3]),'equal flow/area changed held output'
                if cid=='T08-012':assert all(s['ao'][7]==600 for s in rows)
                if cid=='T08-013':
                    assert all(s['ao'][7]==0 and s['do'][3]==0 for s in rows),'min>max not explicitly rejected or safe-disabled'
                if cid=='T08-014':
                    assert rows[-1]['ao'][7]>=800
                    b.stop();b.wr(329,2);b.start();manual=b.observe(cid+' manual',3)
                    assert all(s['ao'][7]==300 and s['ao'][4]==400 for s in manual)
                    extra+=manual
                b.record(cid,'部分通过',f'正常协议配置{cfg}，软件AO采样{[s["ao"][7] for s in rows]}，风速/压差目标和参数值已留证。',
                         '真实输入/端子待补；零设定/倒置范围的规格解释与诊断逐样本保留，未据采样冒充全部判据通过',{'samples':rows,'extra':extra})
            except Exception as e:case_error(b,cid,e)
    finally:b.finish()

if __name__=='__main__':main()
