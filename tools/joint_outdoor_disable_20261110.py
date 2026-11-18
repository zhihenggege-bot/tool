"""Running WJ1 disable controls with normal330 commands; no downstream forcing."""
from joint_priority_20261110 import *


def run():
    b=TodayBench('outdoor_running_disable');e=dict(started=now(),status='running',cases=[],scope='Current legal WJ1 type pair, actual four software heating feedback; normal330 gateway disable inputs, automatic requests; manual path and other pairs separate')
    b.log['continuation_case']=e;b.save()
    def observe(label,pred,timeout=40,hold=2):
        began=time.monotonic();stable=None;rows=[]
        while True:
            s=b.sample(label);s['direct_output']=list(b.ot.read_memory_block8(b.outsy['output'][0],8));s['disables']=[b.ot.read16(b.outsy['Parameter'][0]+2*a) for a in (167,168,169)];s['layer']=b.ot.read16(b.outsy['Parameter'][0]+3002);rows.append(s)
            assert not any(s['faults']),s
            if pred(s):
                if stable is None:stable=time.monotonic()
                if time.monotonic()-stable>=hold:return dict(final=s,samples=rows)
            else:stable=None
            assert time.monotonic()-began<timeout,(label,s)
            time.sleep(.15)
    try:
        b.setup(1);b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,428:0,347:100,348:1,349:0,346:0,320:0,245:1,247:0,329:2,330:0,331:0,365:1,372:350,10:500,12:500})
        pair=tuple(b.ot.read16(b.outsy['Parameter'][0]+2*a) for a in (165,166));e['type_pair']=pair
        pos=((0,0),(0,1),(1,2),(1,3),(2,2),(2,4)).index(pair);unitid=f'O-DISPATCH-{pos*3+1:03d}';compid=f'O-DISPATCH-{pos*3+2:03d}'
        b.temperature(0,220);b.reset_faults();b.start()
        b.wait('running disable four actual heating',lambda s:all(v==3 for p in s['outdoor_status'] for v in p),180)
        for label,settings,wanted in [('compressor1_disabled',{1833:1},[0,1]),('compressor2_disabled',{1833:0,1834:1},[1,0]),('both_compressors_disabled',{1833:1,1834:1},[0,0]),('whole_outdoor_disabled',{1833:0,1834:0,1832:1},[0,0])]:
            r=dict(id=unitid if label=='whole_outdoor_disabled' else compid,label=label,settings=settings,wanted=wanted);e['cases'].append(r)
            for addr,val in settings.items():b.gateway(addr,val)
            r['observation']=observe(label,lambda s:s['direct_output'][:2]==wanted and s['outdoor_status'][1]==[3,3],timeout=120)
            r['status']='软件自动运行子范围通过';print('DISABLE',label,'PASS',wanted,flush=True);b.save()
        for a in (1832,1833,1834):b.gateway(a,0)
        e['allowed_again']=observe('normal automatic requests after clearing disables',lambda s:s['direct_output'][:2]==[1,1] and s['outdoor_status'][1]==[3,3],timeout=180)
        e['status']='completed_automatic_current_pair_only';b.save()
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
