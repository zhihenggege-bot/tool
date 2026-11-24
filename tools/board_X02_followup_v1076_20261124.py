"""Supplement X02 timing and automatic restart without hiding first failed test."""
import json
import time
import traceback
import board_all_DI_v1076_20261124 as all_di


def main():
    original_day=all_di.DAY
    all_di.DAY=original_day/'X02专项复核'
    assert json.loads((original_day/'board.json').read_text('utf8'))['restored']
    b=all_di.Bench()
    try:
        b.setup(return_mode=1,exhaust_mode=0)
        b.config({163:1});b.contact('02',0)
        b.wait('X02 remote input0 stopped without faults',lambda z:z['values'][709]==0 and b.clear(z))
        began=b.contact('02',1)
        z=b.wait('X02 remote filtered input1 starts unit',lambda z:z['values'][709]==2 and b.clear(z),timeout=30)
        b.log['start_total_s']=z['t']-began
        began=b.contact('02',0)
        z=b.wait('X02 direct stop path before3s confirmed',lambda z:z['values'][709] in (3,4,0)
            and z['remote_stop']==0 and b.clear(z),timeout=2,hold=0)
        b.log['remote_stop_request_s']=z['t']-began
        b.check('X02 stop request did not wait3s',z['t']-began<2,elapsed_s=z['t']-began)
        b.wait('X02 sustained input0 completes normal stop without alarm',lambda z:z['values'][709]==0
            and not any(z['indoor_output'][i] for i in (3,6,8)) and b.clear(z),timeout=55)
        began=b.contact('02',1)
        z=b.wait('X02 input restored automatically restarts without fault reset',lambda z:z['values'][709]==2 and b.clear(z),timeout=30)
        b.log['automatic_restart_total_s']=z['t']-began
        b.contact('02',0)
        b.wait('X02 final release normal stop',lambda z:z['values'][709]==0 and b.clear(z),timeout=55)
        b.config({163:0});b.wr(398,0)
        b.log.update(sequence_completed=True,observed_behavior_verified=True,
            acceptance='Control function works;3s-off qualification remains separate specification discrepancy, not passed')
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    b.log['passed']=b.log.get('observed_behavior_verified',False) and b.log.get('restored',False)
    b.save();assert b.log['passed']
    print('X02 SUPPLEMENT PASS observed start/stop/restart;3s-off discrepancy retained;baseline restored',flush=True)


if __name__=='__main__':main()
