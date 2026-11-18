"""Reproduce a legal 0V command lost while old firmware verifies EEPROM.

SWD is used only to observe writer phases; requests are ordinary Modbus writes.
"""
import time,struct,traceback
from run_indoor_bench_20261105 import ControlBench,BOARDS,ConnectHelper,axf_symbols,now


def main():
    b=ControlBench('parameter_race_board_v1048');sy=axf_symbols()
    try:
        b.baseline(2);b.config({329:2,330:0,331:0,134:50});b.wr(398,1)
        b.wait('fan manual5V ready',lambda s:s['state'][9]==2 and s['ao'][7]==500,30)
        with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target
            b.log['trials']=[]
            for attempt in range(20):
                b.wr(134,50)
                end=time.monotonic()+5
                while True:
                    saved=t.read16(sy['Old_Parameter'][0]+2*134)
                    phase=t.read8(sy['EEpflag'][0])
                    if saved==50 and phase==0 and b.rd(134)==[50]:break
                    assert time.monotonic()<end,('cannot establish saved50',saved,phase)
                    time.sleep(.002)
                time.sleep(.02)
                b.c.write_single_register(1,134,100)
                end=time.monotonic()+.7
                observed=False
                while time.monotonic()<end:
                    phase=t.read8(sy['EEpflag'][0])
                    index=t.read16(sy['t'][0])
                    if phase==3 and index==134:
                        observed=True;break
                trial={'at':now(),'attempt':attempt,'observed_verify_window':observed,'samples':[]}
                b.log['trials'].append(trial)
                if not observed:b.save();continue
                b.c.write_single_register(1,134,0)
                start=time.monotonic()
                while time.monotonic()-start<1:
                    trial['samples'].append({'elapsed':time.monotonic()-start,'134':b.rd(134)[0],
                        'DA7':b.rd(921)[0],'writer_state':t.read8(sy['EEpflag'][0]),
                        'write_error':t.read16(sy['CPURomWriteError'][0])})
                    time.sleep(.02)
                trial['lost_zero_request']=any(s['134']!=0 for s in trial['samples'])
                trial['result']='latest valid0V command reverted' if trial['lost_zero_request'] else 'zero request retained'
                b.save();print('TRIAL',attempt,trial['result'],trial['samples'][-1],flush=True)
                if trial['lost_zero_request']:
                    b.log['reproduced']=True;break
            b.log.setdefault('reproduced',False)
            b.save()
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()


if __name__=='__main__':main()
