"""Resolve refresh-counter audit finding without rewriting original evidence."""
import full_queue_context_20261113 as ctx
import time

def main():
    old=ctx.json.loads((ctx.DAY/'deployment.json').read_text('utf8'))
    assert all(x.get('flash_verified') for x in old['boards'])
    assert old['boards'][2]['programmed']
    c=ctx.runtime.client()
    q=dict(at=ctx.now(),original_journal='deployment.json',read_only=True)
    try:
        q['versions']=c.read_holding_registers(1,2622,18)
        assert q['versions']==ctx.runtime.EXPECTED
        q['profile']=c.read_holding_registers(1,1298,2)
        assert q['profile']==[3,15107]
        q['changes']={}
        for a,n in [(0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2),(1319,26),(1389,11),(1830,96),(2680,98)]:
            for i,v in enumerate(c.read_holding_registers(1,a,n)):
                key=str(a+i)
                if v!=old['config_before'][key]:q['changes'][key]=[old['config_before'][key],v]
        allowed={167:'runtime',373:'runtime',1875:'unit1 gateway refresh counter',1923:'unit2 gateway refresh counter'}
        assert not (set(map(int,q['changes']))-set(allowed)),q['changes']
        q['change_explanations']={a:allowed[int(a)] for a in q['changes']}
        q['snapshot']=ctx.runtime.snap(c)
        assert c.read_holding_registers(1,398,1)==[0] and q['snapshot']['state'][9]==0 and ctx.loads_off(q['snapshot'])
        q['verified']=True
        ctx.dump(ctx.DAY/'deployment_counter_review.json',q)
    finally:c.close()
    for name in ('continuous_v1055_pause.request','fan_minrun_spotcheck_pause.request'):
        marker=ctx.R/'.codex-tmp'/name
        if marker.exists():marker.replace(ctx.DAY/(name+'.before_authorized_resume'))
    ctx.dump(ctx.DAY/'resume_authorization.json',dict(at=ctx.now(),instruction='接着测试！认真烧录测试！',versions=q['versions'],profile=q['profile']))
    b=ctx.current_bench_class()('recover_interrupted_v1058_today_stopped_baseline')
    try:
        b.log['before_normal_reset']=b.detailed('overnight alarm evidence before normal reset')
        b.save()
    finally:b.finish()
    assert b.log.get('restored')
    import bench_current_20261112 as dispatch
    dispatch.DAY,dispatch.I,dispatch.BOARDS=ctx.DAY,ctx.I,ctx.BOARDS
    dispatch.current_bench_class=ctx.current_bench_class
    dispatch.audit('today_pretest_restoration')
    print('DEPLOYMENT AND STOPPED BASELINE VERIFIED',flush=True)

if __name__=='__main__':main()
