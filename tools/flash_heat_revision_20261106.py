"""Exclusive stopped-board update; 316 read only, 330 version10.53 BENCH."""
from heat_dynamic_board_20261106 import *
import run_indoor_bench_20261105 as r
from pyocd.flash.file_programmer import FileProgrammer

def main():
    assert r.EXPECTED[2]==53
    path=D/'flash_heat_display_20261106.json';assert not path.exists()
    report={'at':now(),'programmed_boards':['330'],'outdoor_changed':False,'boards':[]}
    old=R/'测试证据/内机实测_20261105/BENCH_V1052_V1239'
    # Retain every original failure and preceding-version test result.
    RESULTS.write_bytes((old/'case_results.json').read_bytes())
    c=r.client()
    try:
        assert c.read_holding_registers(1,2622,18)==[330,10,52,2026,11,5,316,12,39,2026,11,5,316,12,39,2026,11,5]
        report['before_snapshot']=r.snap(c)
        assert report['before_snapshot']['state'][9]==0 and loads_off(report['before_snapshot'])
        cfg={}
        for a,n in ((0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2)):
            cfg.update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        report['config']=cfg;dump(D/'preflight.json',report);dump(path,report)
    finally:c.close()
    for label,uid,target,device,flash_size,ram_size,stem in r.BOARDS:
        image=I/(stem+'.hex');mem=r.parse_hex(image)
        entry={'board':label,'uid':uid,'sha256':r.sha(image),'programmed':False,'verified_bytes':0}
        report['boards'].append(entry);dump(path,report)
        with ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target;assert t.read32(0xE0042000)&0xfff==device
            if label=='330':
                t.halt();debugreg=0xE0042008;old_debug=t.read32(debugreg)
                try:
                    for name,addr,n in (('flash',0x08000000,flash_size),('sram',0x20000000,ram_size)):
                        p=D/('330_before_display_fix_'+name+'.bin');assert not p.exists()
                        p.write_bytes(bytes(t.read_memory_block8(addr,n)))
                        entry[name+'_backup']={'file':p.name,'sha256':r.sha(p)}
                    t.write32(debugreg,old_debug|0x1800);t.reset_and_halt()
                    t.write32(debugreg,t.read32(debugreg)|0x1800)
                    FileProgrammer(ss,chip_erase='sector',trust_crc=False).program(str(image))
                    entry['programmed']=True
                    for lo,hi in r.blocks_of(mem):
                        for a in range(lo,hi,2048):
                            got=bytes(t.read_memory_block8(a,min(2048,hi-a)))
                            assert got==bytes(mem[x] for x in range(a,a+len(got)))
                            entry['verified_bytes']+=len(got)
                finally:t.write32(debugreg,old_debug);t.reset()
            else:
                for lo,hi in r.blocks_of(mem):
                    for a in range(lo,hi,2048):
                        got=bytes(t.read_memory_block8(a,min(2048,hi-a)))
                        assert got==bytes(mem[x] for x in range(a,a+len(got)))
                        entry['verified_bytes']+=len(got)
            entry['flash_verified']=True;dump(path,report)
            print('FLASH VERIFIED',label,'programmed',entry['programmed'],entry['verified_bytes'],flush=True)
    c=r.client()
    try:
        end=time.monotonic()+45
        while True:
            try:v=c.read_holding_registers(1,2622,18)
            except Exception:v=[]
            if v==r.EXPECTED:break
            assert time.monotonic()<end,v;time.sleep(.3)
        sy=axf_symbols()
        with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            while ss.target.read8(sy['IndoorAiCfgLoaded'][0])!=1 or ss.target.read8(sy['eepromtt'][0])!=3:
                assert time.monotonic()<end;time.sleep(.2)
        actual={}
        for a,n in ((0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2)):
            actual.update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
        report['config_after']=actual
        report['config_changes']={k:[v,actual[k]] for k,v in cfg.items() if v!=actual[k] and int(k) not in (167,373)}
        assert not report['config_changes'],report['config_changes']
        report['versions_after']=v;report['snapshot_after']=r.snap(c)
        assert report['snapshot_after']['state'][9]==0 and loads_off(report['snapshot_after'])
        report['passed']=True;report['finished']=now();dump(path,report)
    finally:c.close()
    print('DISPLAY FIX FLASH COMPLETE; original configuration matches',flush=True)

if __name__=='__main__':main()
