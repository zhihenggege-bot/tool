"""Independent verdict from raw observations; unavailable6 is not a request."""
from joint_precondition_20261110 import *
import argparse

def main():
    ap=argparse.ArgumentParser();ap.add_argument('journal',type=Path);a=ap.parse_args()
    j=json.loads(a.journal.read_text('utf8'));e=j['priority_case']
    q=dict(at=now(),source=str(a.journal),original_runner_status=e.get('status'),scope='Independent interpretation of untouched raw observations; phase6 is unavailable, not a request')
    first=e['qualified_at12'];hold=e['after_qualified_hold12'];control=e['cooler_request']
    def qualified(x,temp):
        p=x['params']
        return (p['182']==150 and p['183']==20 and p['185']==5 and signed16(p['1422'])==temp
            and p['617']==1 and p['612']==0 and x['output'][1]==1 and x['CompRunTime'][1]>=300
            and x['DefGapCount'][1]>=1200 and x['TimedEnvLowCount'][0]>=60 and x['TimerDefrostMode'][1]==1)
    held=[x for x in e['diagnostics'] if first['t']<=x['t']<=hold['t']]
    q['qualified_12C_hold_seconds']=hold['t']-first['t']
    q['qualified_12C_samples']=len(held)
    q['all_12C_preconditions_hold']=all(qualified(x,120) for x in held)
    q['no_healthy_system_request_at12']=all(x['params']['1421']==0 for x in held)
    q['faulted_system_unavailable_not_request']=all(x['params']['1420']==6 for x in held)
    q['9C_request_phase']=control['params']['1421']
    q['9C_request_after_input_seconds']=control['t']-next(x['t'] for x in e['diagnostics'] if x['t']>hold['t'] and signed16(x['params']['1422'])==90)
    q['verdict']='不符合：15℃定时门槛设置时，12℃全部前置满足仍无请求，降9℃后请求出现' if q['qualified_12C_hold_seconds']>=19 and q['all_12C_preconditions_hold'] and q['no_healthy_system_request_at12'] and q['9C_request_phase'] in (1,5,7,8) else '证据不足或未复现；逐项检查原始条件'
    q['source_cause']='DefEnable()定时分支在可设150的温度门槛之后，再以EnviTempAI0Disp<100决定StartOK，形成额外固定10℃限制。'
    dest=a.journal.with_name(a.journal.stem+'_independent_verdict.json');dump(dest,q);print(json.dumps(q,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
