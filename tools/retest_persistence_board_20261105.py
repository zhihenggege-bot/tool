"""Normal Modbus updates at observed EEPROM phases, followed by a full boot reset."""
import time,struct,traceback
from run_indoor_bench_20261105 import ControlBench,BOARDS,ConnectHelper,axf_symbols,now,result

def main():
    b=ControlBench('persistence_fixed');sy=axf_symbols();b.log['trials']=[]
    try:
        b.baseline(2);b.config({329:2,330:0,331:0,134:50});b.wr(398,1)
        b.wait('manual5V',lambda s:s['state'][9]==2 and s['ao'][7]==500,30)
        with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target
            for attempt in range(30):
                b.wr(134,50);end=time.monotonic()+8
                while not (t.read16(sy['Old_Parameter'][0]+268)==50 and t.read8(sy['EEpflag'][0])==0):
                    assert time.monotonic()<end,'saved50 not established';time.sleep(.003)
                time.sleep(.02);b.c.write_single_register(1,134,100)
                end=time.monotonic()+.8;observed=False
                while time.monotonic()<end:
                    phase=t.read8(sy['EEpflag'][0]);index=t.read16(sy['t'][0])
                    if phase==3 and index==134:observed=True;break
                item={'attempt':attempt,'observed_verify_window':observed,'samples':[]};b.log['trials'].append(item)
                if not observed:continue
                b.wr(134,0);start=time.monotonic()
                while time.monotonic()-start<.5:
                    v={'elapsed':time.monotonic()-start,'parameter134':b.rd(134)[0],
                       'DA7':b.rd(921)[0],'error':t.read16(sy['CPURomWriteError'][0])}
                    item['samples'].append(v);assert v['parameter134']==0 and v['DA7']==0,v
                    time.sleep(.015)
                assert t.read16(sy['Old_Parameter'][0]+268)==0,'latest zero not persisted'
                b.save();print('RACE RETEST',attempt,'zero retained and saved',flush=True)
                if sum(v['observed_verify_window'] for v in b.log['trials'])>=20:break
            b.log['observed_race_trials']=sum(v['observed_verify_window'] for v in b.log['trials'])
            assert b.log['observed_race_trials']>=10,b.log['trials']
            b.stop()
            # Update AI after the prior snapshot has started, while also changing normal words.
            b.wr(1237,10);end=time.monotonic()+15
            while t.read8(sy['IndoorAiStState'][0])!=1:
                assert time.monotonic()<end,'AI save window not reached';time.sleep(.005)
            b.wr(1237,20)
            b.log['concurrent_ai_update']={'at':now(),'newest_offset':20,'journal_phase':1}
            for a in (134,131,328,132,135):
                for value in (0,10,50,30):b.wr(a,value)
            wanted={a:b.rd(a)[0] for a in (134,131,328,132,135,1237)}
            end=time.monotonic()+20;stable=None
            while True:
                normal=all(t.read16(sy['Old_Parameter'][0]+2*a)==v for a,v in wanted.items() if a<500)
                ai=t.read16(sy['IndoorAiCfgShadow'][0]+16)==20 and t.read8(sy['IndoorAiCfgDirty'][0])==0
                ready=normal and ai and t.read8(sy['EEpflag'][0])==0 and t.read8(sy['IndoorAiStState'][0])==0
                if ready:
                    stable=stable or time.monotonic()
                    if time.monotonic()-stable>=1:break
                else:stable=None
                assert time.monotonic()<end,('not saved',normal,ai,ready);time.sleep(.1)
            b.log['saved_before_reset']=wanted;b.save();t.reset()
            end=time.monotonic()+30
            while not(t.read8(sy['IndoorAiCfgLoaded'][0])==1 and t.read8(sy['eepromtt'][0])==3):
                assert time.monotonic()<end,'boot not complete';time.sleep(.25)
            actual={a:b.rd(a)[0] for a in wanted}
            b.log['reset_readback']=actual;assert actual==wanted,(wanted,actual)
            b.log['passed']=True;b.save();print('RESET newest normal/AI values retained',actual,flush=True)
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    print('PERSISTENCE HARDWARE PASS',b.path,flush=True)

if __name__=='__main__':main()
