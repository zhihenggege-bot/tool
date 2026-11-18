"""V10.51 real-board diagnostic and Z0 follow-up; normal protocol only."""
import time,traceback
from remaining571_common_20261105 import Bench,now,case_error
def main(only_reheat=None):
    b=Bench('v1051_targeted')
    try:
        b.setup(0);b.config({329:2,320:1,315:1,327:0,38:0})
        b.start();rows=b.observe('invalid ambient, auto enabled',3)
        # The later configured-output guard may replace unload=4 with hold=0;
        # either leaves no compressor request. Do not mistake that guard for a fault.
        assert all(s['diag'][21]==6 and s['diag'][9]==0 and s['state'][7] in (0,4) and not any(x in (2,3,4) for u in s['outdoor_status'] for x in u) for s in rows),rows[-1]
        b.wr(320,0);rows2=b.observe('invalid ambient, auto disabled',3)
        assert all(s['diag'][21]==7 for s in rows2),rows2[-1]
        b.wr(320,1);rows3=b.observe('auto enabled again',3)
        assert all(s['diag'][21]==6 for s in rows3)
        b.record('T11-102','部分通过','当前板上环境负荷非法组合自动切换启用时原因6稳定；关闭自动切换后7，重新启用回6；目标0、外机请求清零，未启压机。',
                 '真实合法环境控制及切换长计时矩阵待补；本例验证修复涉及诊断稳定性',{'auto_on':rows,'off':rows2,'on_again':rows3})
        for reheat,cid in ((0,'T09-025'),(1,'T09-028')):
            if only_reheat is not None and reheat!=only_reheat:continue
            entry={'started':now(),'reheat':reheat};b.log['cases'][cid]=entry
            try:
                b.setup(0);b.config({42:3,43:180,214:3,250:1,251:1,252:1,253:1,
                                    125:0,127:reheat,332:reheat,128:2,129:1,412:5,416:5,417:100,418:0,
                                    160:250,161:250})
                b.ntc(0,280);b.ntc(2,160);b.reset_faults();b.start()
                entry['running']=b.wait(cid+' two actual',lambda s:b.rd(119)[0]==2 and s['state'][9]==2,120)
                # Hold actual running machines using the public minimum-run setting.
                # Negative PID may request unloading but eligibility must block it.
                b.config({412:1,416:100,417:1});b.ntc(0,220)
                entry['zero_N']=b.wait(cid+' demand zero actual2',lambda s:b.rd(880)[0]==0 and b.rd(119)[0]==2,15)
                b.ntc(0,250)
                entry['hold']=b.wait(cid+' Z0 actual2 target2',lambda s:b.rd(879)[0]==0 and b.rd(880)[0]==0 and b.rd(881)[0]==2 and b.rd(119)[0]==2 and s['state'][7]==0,15)
                rows=b.observe(cid+' stable hold',5)
                assert all(s['count_119']==2 and s['diag'][9]==2 and s['state'][7]==0 for s in rows)
                assert not any(w['address'] in (118,119,880,881) for w in b.log['writes'])
                # The experiment is complete. Restore the BENCH minimum-run
                # setting through its public parameter before ordinary shutdown.
                b.wr(43,3)
                b.record(cid,'部分通过',f'再热{reheat}；正常压机请求建立实际2台，公开最短运行参数180秒保持；正常温度校准使N=0/Z=0后目标=实际=2，连续5秒保持，指令0。',
                         '本轮为软件输出；真实温度信号和端子待补；所有输入/最短运行参数于批末恢复',entry)
            except Exception as e:case_error(b,cid,e)
    except BaseException:
        b.log['host_or_test_error']=traceback.format_exc();b.save();raise
    finally:b.finish()
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--only-reheat',type=int)
    main(p.parse_args().only_reheat)
