"""Public-protocol configuration compatibility; no GUI/terminal claims."""
import time,traceback
from remaining571_common_20261105 import Bench,case_error,now
from app import Psc330MonitorApp

def main():
    b=Bench('config')
    def ui(cfg):
        vals={i:0 for i in range(500)}
        vals.update({329:2,330:2,331:1,340:100,341:30,342:100,383:100,384:50,356:0,357:-50})
        vals.update(cfg)
        try:Psc330MonitorApp._validate_mode_config(vals);return {'accepted':True}
        except ValueError as e:return {'accepted':False,'error':str(e)}
    try:
        cases=[('T07-001',{128:1,127:0,332:1,129:1},0,None),
               ('T07-002',{128:1,127:1,332:1,129:1},0,None),
               ('T07-003',{330:2,329:1,336:2},2,6),
               ('T07-004',{330:2,337:2},2,6),
               ('T07-005',{329:2,336:2},1,3),
               ('T07-006',{329:3,336:2},1,3),
               ('T07-008',{335:2,377:1,381:1},0,None),
               ('T07-009',{335:1,377:2,381:1},32,None),
               ('T07-010',{338:2,335:2,377:1},0,None),
               ('T07-011',{338:2,335:1,377:2},32,None),
               ('T07-012',{315:1,327:0},64,None)]
        for cid,cfg,mask,di in cases:
            try:
                b.setup(2);b.config(cfg)
                if cfg.get(377)==1:
                    b.ai(1,500);b.ai(2,1000);b.ai(4,500)
                b.wr(398,1);time.sleep(6);rows=b.observe(cid,2)
                flags=b.rd(940)[0];entry={'config':cfg,'ui_function_check':ui(cfg),'samples':rows,'flags':flags}
                if mask:assert flags&mask,(cid,'diagnostic missing',flags,mask)
                if di is not None:assert all(s['do'][di]==0 for s in rows)
                if cid=='T07-008':assert all(s['ao'][3]+s['ao'][5]==1000 for s in rows)
                if cid=='T07-009':assert all(s['ao'][5]==0 for s in rows)
                if cid=='T07-010':assert all(s['ao'][6]==s['ao'][3] for s in rows)
                if cid=='T07-011':assert all(s['ao'][6]==0 for s in rows)
                b.record(cid,'部分通过',f'公开配置{cfg}，940={flags:#x}；软件输出已采集；Python校验函数'+('允许' if entry['ui_function_check']['accepted'] else '拒绝'),
                         '仅固件协议/软件输出及Python校验函数；实际Python界面联动、MCGS页面和物理端子均待验；热泵负载许可未由配置通过替代',entry)
            except Exception as e:case_error(b,cid,e)
        cid='T07-007';allrows=[]
        try:
            b.setup(2)
            for heat in (3,4,5):
                for reheat in (2,3,4):
                    cfg={129:0,128:heat,127:1,332:reheat};b.config(cfg);time.sleep(.2)
                    flags=b.rd(940)[0];allrows.append({'config':cfg,'940':flags,'ui':ui(cfg)})
                    assert flags&16 and not allrows[-1]['ui']['accepted'],allrows[-1]
            b.record(cid,'部分通过','独立主热3/4/5 × 再热2/3/4共9个冲突组合，940均包含0x10，Python校验函数均拒绝。',
                     '未启负载；未点实际Python/MCGS界面；输出禁止和端子矩阵待补',{'combinations':allrows})
        except Exception as e:case_error(b,cid,e)
        cid='T07-013'
        try:
            b.setup(1);samples=[]
            for preheat in (2,3,4):
                b.config({374:1,333:preheat});time.sleep(.3);samples.append({'preheat':preheat,'940':b.rd(940)[0]})
            b.record(cid,'部分通过','后温预热PID+分段/SCR三组合已通过协议写入并采集冲突诊断：'+str(samples),
                     '是否明确拒绝/降级与页面提示仍需逐项判定；未以写入成功认定符合',{'samples':samples})
        except Exception as e:case_error(b,cid,e)
        for basis,cid in ((0,'T07-028'),(1,'T07-029'),(2,'T07-030')):
            try:
                b.setup(2);b.config({335:2,377:basis,378:10,379:1000,381:int(basis==1),338:2 if basis==1 else 0})
                b.ai(0,10);b.ai(1,500);b.ai(2,1000);b.ai(4,500)
                b.start();rows=[]
                if basis==2:
                    for volt in (0,50,100):
                        b.wr(380,volt);time.sleep(.3);s=b.sample(cid+' manual');rows.append(s)
                        assert s['ao'][3]==volt*10,s
                else:
                    ch=0 if basis==0 else 2
                    for val in ((0,10,20) if basis==0 else (500,1000,1500)):
                        b.ai(ch,val);rows+=b.observe(cid+' feedback',2)
                    if basis==1:assert all(s['ao'][3]+s['ao'][5]==1000 and s['ao'][6]==s['ao'][3] for s in rows)
                b.stop()
                b.record(cid,'部分通过',f'新风AO依据{basis}：正常工程量映射刺激，AO序列{[s["ao"][3] for s in rows]}；'+('手动0/5/10V软件值正确' if basis==2 else '方向/互补/跟随样本留证'),
                         '工程映射不是物理信号；焓差全组合、房压方向细判、页面和端子待补',{'samples':rows})
            except Exception as e:case_error(b,cid,e)
    finally:b.finish()
if __name__=='__main__':main()
