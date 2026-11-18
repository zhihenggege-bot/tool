"""Restore only the B03 high-pressure fixture spans to their captured values."""
from joint_v1058_context_20261111 import DAY, BOARDS, runtime, ConnectHelper, dump, now
from joint_precondition_20261110 import symbols
import json
import time
import traceback


def run():
    path=DAY/('B03_ai_restore_'+time.strftime('%H%M%S')+'.json')
    expected={}
    for old in sorted(DAY.glob('B03_pressure_fan_*.json'),key=lambda p:json.loads(p.read_text('utf8'))['fixed_vfd']['started']):
        values=json.loads(old.read_text('utf8'))['fixed_vfd']['ai_original']
        for key,value in values.items():expected.setdefault(int(key),value)
    assert expected=={2684:0,2685:5000,2696:0,2697:5000},expected
    q=dict(started=now(),expected=expected,samples=[],verified=False);dump(path,q)
    c=runtime.client()
    rd=lambda a,n=1:c.read_holding_registers(1,a,n)
    try:
        assert rd(2622,18)==runtime.EXPECTED and rd(1298,2)==[3,15107]
        assert rd(398)==rd(709)==[0] and not any(rd(2598,2))
        assert runtime.loads_off(runtime.snap(c))
        board=BOARDS[0]; sy=symbols(board); p=sy['Parameter'][0]
        with ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target;assert not any(t.read_memory_block8(*sy['output']))
            direct=lambda a:t.read16(p+2*(302+a-2680))
            q['before']={a:[direct(a),rd(a)[0]] for a in expected};dump(path,q)
            for a,v in expected.items():
                if direct(a)==rd(a)[0]==v:continue
                end=time.monotonic()+20
                while rd(1873)==[1]:
                    assert time.monotonic()<end,'AI gateway busy';time.sleep(.3)
                try:c.write_single_register(1,a,v)
                except Exception as exc:q.setdefault('write_exceptions',[]).append(repr(exc))
                end=time.monotonic()+60
                while True:
                    z=dict(at=now(),address=a,direct=direct(a),mirror=rd(a)[0],diag=rd(1872,6));q['samples'].append(z)
                    if z['direct']==z['mirror']==v and z['diag'][1]!=1:break
                    assert time.monotonic()<end,('restore timeout',z);time.sleep(.4)
            q['after']={a:[direct(a),rd(a)[0]] for a in expected}
            assert q['after']=={a:[v,v] for a,v in expected.items()}
            assert not any(t.read_memory_block8(*sy['output']))
            q['verified']=True
    except Exception:
        q['error']=traceback.format_exc();raise
    finally:
        c.close();q['finished']=now();dump(path,q);print('AI RESTORE',path,q['verified'],flush=True)


if __name__=='__main__':run()
