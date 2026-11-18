"""Normal-protocol zero special stages, pressure options and separate WD values."""
import time
from remaining571_common_20261105 import Bench,case_error
from run_indoor_bench_20261105 import axf_symbols,BOARDS,ConnectHelper,loads_off

def main():
    b=Bench('529_configuration')
    try:
        for mode,cid in ((3,'T13-041'),(4,'T13-042'),(5,'T13-045')):
            try:
                b.setup(mode)
                b.config({323:0,324:0,325:0})
                b.wr(398,1)
                rows=b.observe(cid+' disabled special stages',8)
                assert all(loads_off(s) and s['do'][10]==0 for s in rows),rows[-1]
                assert rows[-1]['state'][9]==0,rows[-1]
                b.record(cid,'部分通过',f'模式{mode}、消毒/排毒时间均0，正常开机命令后观察8s：未启动消毒、风机及冷热负载，最终步骤0。',
                    'BENCH普通协议/软件输出；真实端子和非零阶段原状不属本例',{'samples':rows})
            except Exception as e:case_error(b,cid,e)
            b.stop()
        sy=axf_symbols()
        with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            def contact(ch,value):
                reg=397 if ch==15 else 396
                raw=lambda:ss.target.read8(sy['X_'+str(ch)][0])
                if raw()!=value:b.wr(reg,1-b.rd(reg)[0])
                end=time.monotonic()+5
                while raw()!=value:
                    assert time.monotonic()<end,(ch,value,raw())
                    time.sleep(.1)
            for cfg in range(4):
                cid=f'T04-{7+cfg:03d}'
                try:
                    runs=[]
                    for returning in (0,2):
                        b.setup(2)
                        b.config({386:cfg,330:returning})
                        # Unfitted channels deliberately open; fitted ones closed.
                        contact(15,int(cfg in (1,2)))
                        contact(14,int(cfg in (1,3) and returning!=0))
                        b.reset_faults()
                        s=b.start()
                        assert s['do'][3]==1 and s['do'][6]==int(returning!=0),s
                        rows=b.observe(cid+' fitted versus absent',4)
                        assert all(s['state'][9]==2 and b.rd(912,2)==[0,0] for s in rows)
                        runs.append({'return_config':returning,'running':s,'hold':rows})
                        b.stop()
                    b.record(cid,'部分通过',f'压差配置{cfg}，分别配置无回风机/手动AO回风机：已配置触点以极性模拟闭合，未配置触点保持断开，两组合均能完成启动且观察4s无误报。',
                        '极性模拟/软件回读；未配置触点60+10s长断开、真实接点和正式起机10s另验',{'runs':runs})
                except Exception as e:case_error(b,cid,e)
                b.stop()
        cid='T07-084'
        try:
            rows=[]
            for mode in (0,1):
                b.setup(mode)
                b.config({160:260,161:230})
                b.ntc(0,250)
                b.start()
                s=b.sample(cid+' mode WD')
                assert b.rd(739)[0]==(260 if mode==0 else 230),s
                rows.append(s)
                b.stop()
            b.record(cid,'部分通过','冷/热设置160=26℃、161=23℃，分别按正常模式启动后实际WD[739]为260/230，双温度设定切换生效。',
                '当前普通模式回读；本例独立复位和真实断电后保留未测',{'modes':rows})
        except Exception as e:case_error(b,cid,e)
        b.log['passed']=not any('error' in v for v in b.log['cases'].values())
    finally:b.finish()
    print('CONFIGURATION COMPLETE',b.path,flush=True)

if __name__=='__main__':main()
