"""Legacy DA8 isolation characterization in fixed-compressor cooling mode."""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench,paused


def main():
    b=CheckedBench('legacy_da8_isolation');e=dict(passed=False,phases=[],
        scope='Fixed-compressor selection, normal legacy manual parameters; no asserted chilled-water medium permission, software AO only')
    b.log['cases']['T06-024']=e;b.save()
    try:
        b.setup(0);b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,315:0,320:0,346:0,
            245:1,247:0,329:2,330:0,331:0})
        b.temperature(0,250);b.reset_faults();b.start()
        # [314] is forced back to0 by this branch. A first request for1
        # failed readback; preserve that attempt, do not invent a media mode.
        for select,manual in ((0,0),(0,500),(0,0)):
            paused();b.config({314:select,247:manual});time.sleep(.6)
            p=dict(legacy_DA0_select=select,manual_DA8_value=manual,samples=[]);e['phases'].append(p)
            began=time.monotonic()
            while time.monotonic()-began<4:
                s=b.snapshot('legacy DA8 selected fixed compressors');s.update(legacy_select=b.rd(314)[0],legacy_manual=b.rd(245,3),da8_display=b.rd(925)[0],actual_count=b.rd(119)[0]);p['samples'].append(s)
                assert not any(s['faults']) and s['state'][9]==2,s
                time.sleep(.15)
            b.save();print('DA8 ISOLATION',select,manual,[s['ao'][8] for s in p['samples']],flush=True)
        offending=[s for p in e['phases'] for s in p['samples'] if s['ao'][8]!=0]
        e['nonzero_without_explicit_medium_permission']=offending;e['passed']=not offending;b.save()
        b.record_local('T06-024',e['passed'],
            'V10.55固定压机配置、制冷室温等于设定值25℃，未设置独立冷水介质/DA8启用许可；正常旧参数[245]=手动，[247]0→500→0，[314]保持本分支实际固定0，各观察4s。'+
            ('DA8始终0。' if e['passed'] else f'发现{len(offending)}组非零DA8样本：仅旧手动参数即可输出500；[314]在本分支固定回0，不能作为独立介质启用许可，首次请求1的回读失败另留证。判T06-024软件隔离不满足，保留原轨迹待定向整改。')+
            '未写AO/需求/压机状态；端子及冷水介质算法未验。',e)
        data=json.loads(RESULTS.read_text('utf8'));data['T06-024']['inputs']='Normal legacy parameters245/247 and314, fixed-compressor cooling; no output forcing';dump(RESULTS,data)
        e['normal_stop']=b.stop();assert loads_off(e['normal_stop'])
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:b.finish()


if __name__=='__main__':main()
