"""Legal heat/preheat output combinations and inactive reheat ownership."""
from heat_dynamic_board_20261106 import *

def power(kind,n,ao,groups):
    if kind==1:return ao==n and groups==[0,0,0]
    if kind in (2,3):return ao==0 and (groups[2]==0 if kind==2 else True)
    return groups[2]==0 and abs(ao*4+3000*(groups[0]+groups[1])-n*10)<=2

def main():
    b=HeatBench('parallel');entry={'combinations':[],'note':'Main heat/reheat are mode alternatives, not three simultaneous PID controllers.'}
    try:
        config_heat(b,'main',1)
        # Full preheat avoids claiming independent DO ownership while its
        # stages are still off. Zero Celsius is legal and avoids the separate
        # below-zero minimum-valve rule.
        b.temperature(2,0)
        for heat in range(1,5):
            for preheat in range(1,5):
                b.config({128:0,333:0,127:0,129:0,332:1})
                time.sleep(.25)
                off=b.sample_heat('reset heat output selection')
                assert off['heat']==off['preheat']==0 and all(off['ao'][i]==0 for i in (0,1,9))
                b.config({128:heat+1,333:preheat,374:0,356:100,357:0,
                    347:100,348:1,349:0,346:0})
                b.temperature(0,240)
                group={'heat_mode':heat,'preheat_mode':preheat,'rows':[],'passed':True}
                began=time.monotonic()
                while time.monotonic()-began<11:
                    s=b.sample_heat('parallel main'+str(heat)+' preheat'+str(preheat));group['rows'].append(s)
                    expected_pre=s['preheat']
                    ok=(s['ao'][9]==0 and power(heat,s['heat'],s['ao'][0],s['do'][:3]) and
                        power(preheat,expected_pre,s['ao'][1],s['do'][13:16]) and not s['conflict'])
                    # First sample may precede a conversion or PID history.
                    # Actual requests are recorded rather than assumed full.
                    group['passed']&=ok
                    time.sleep(.12)
                assert any(s['heat']>=900 and s['preheat']==1000 for s in group['rows']),group
                entry['combinations'].append(group);b.log['parallel']=entry;b.save()
                print('PARALLEL',heat,preheat,'PASS',group['passed'],flush=True)
        b.stop()
        # Cooling independent reheat uses DA9 (or its stage DOs); a configured
        # preheater must remain inactive because PreHeatControl permits HEAT.
        config_heat(b,'independent',1)
        b.config({347:100})
        for kind in range(1,5):
            b.config({332:0,333:4});time.sleep(.2)
            b.config({332:kind});b.temperature(0,240)
            group={'independent_reheat_mode':kind,'rows':[],'passed':True}
            began=time.monotonic()
            while time.monotonic()-began<10:
                s=b.sample_heat('cool independent reheat and configured preheater');group['rows'].append(s)
                group['passed']&=(s['preheat']==0 and s['ao'][0]==0 and s['ao'][1]==0 and
                    s['do'][13:16]==[0,0,0] and power(kind,s['heat'],s['ao'][9],s['do'][:3]))
                time.sleep(.12)
            assert any(s['heat']>=900 for s in group['rows'])
            entry['combinations'].append(group);b.save()
            print('INDEPENDENT',kind,'PASS',group['passed'],flush=True)
        b.stop()
        # Both independently configured stage heaters share Y00/Y01/Y02 and
        # must be rejected; main/preheat SCR uses different DOs and is legal.
        b.setup(0);b.config({128:5,127:1,129:0,332:4,333:4,374:0,346:0})
        b.temperature(0,240);b.start();rows=b.observe('forbidden independent stage conflict',4)
        entry['forbidden_stage_samples']=rows
        entry['forbidden_stage_passed']=all(s['conflict'][0]&16 and s['ao'][0]==s['ao'][1]==s['ao'][9]==0 and s['do'][:3]==[0,0,0] for s in rows)
        ok=all(x['passed'] for x in entry['combinations']) and entry['forbidden_stage_passed']
        b.record_local('T06-023',ok,
            f'板上16组主热×预热AO/1:2/1:2:4/SCR合法并行及4种冷态独立再热隔离；成功{sum(x["passed"] for x in entry["combinations"])}/20组；非法双独立分段抑制={entry["forbidden_stage_passed"]}。主热与再热按工作模式交接，未声称三套同时开启。',entry)
    except Exception:
        entry['error']=traceback.format_exc();b.log['parallel']=entry;b.save();raise
    finally:
        b.finish();print('PARALLEL RESTORED',b.log.get('restored'),b.path,flush=True)

if __name__=='__main__':main()
