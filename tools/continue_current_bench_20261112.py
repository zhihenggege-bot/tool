"""One hardware writer: run, recover, independently audit, then continue."""
import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
DAY=ROOT/'测试证据/台架执行_20261112'
PAUSE=ROOT/'.codex-tmp/continuous_v1055_pause.request'

def stamp():return time.strftime('%Y-%m-%dT%H:%M:%S%z')

def tasks():
    plan=[('fixed_two_speed_heating',['heat3'])]
    plan += [(f'fixed_variable_minrun_{v}',['minrun','--value',str(v)]) for v in (10,30,60,120,300)]
    plan += [('fixed_two_speed_cooling_spec',['typeII'])]
    def add(key,script,*args):plan.append((key,['legacy','tools/'+script,*args]))
    add('pressure_sensor_mirrors','bench_remaining_adc_20261111.py','pressure')
    add('contact_protection_mirrors','bench_remaining_adapter_20261111.py','contacts')
    add('gateway_contention','bench_remaining_gateway_20261111.py')
    for index in (2,4,5,0,1):add('heating_dispatch_'+str(index),'bench_remaining_outdoor_20261111.py','heat',str(index))
    for case in ('lws22','lws25','rws18','rws10','heatlow','type2high'):
        add('ambient_'+case,'bench_remaining_outdoor_20261111.py','ambient',case)
    add('indoor_ventilation_AI','bench_remaining_adc_20261111.py','ventilation')
    add('indoor_coil_real_seconds','bench_remaining_adapter_20261111.py','coils')
    add('indoor_winter_boundaries','bench_remaining_adapter_20261111.py','winter')
    add('indoor_DA8_observation','bench_remaining_da8_20261111.py')
    add('analog_HP_threshold','bench_remaining_pressure_trip_20261111.py')
    for kind in ('disable','mode'):add('defrost_'+kind,'bench_remaining_outdoor_20261111.py','defrost',kind)
    for kind in ('fault1','fault2','fault-both','fan-fault','disable1','disable2','disable-both','hp2','lp-startup','lp-defrost','mirror-unit2'):
        add('defrost_matrix_'+kind,'bench_remaining_defrost_matrix_20261111.py',kind)
    for channel in (0,1):add('defrost_analog_HP_'+str(channel),'bench_remaining_defrost_analog_20261111.py',str(channel))
    add('defrost_partner30','bench_remaining_defrost_partner_20261111.py')
    add('defrost_natural_two_board_arbitration','bench_remaining_defrost_arbiter_20261111.py')
    for kind in ('normal','timed','negative'):add('defrost_natural_'+kind,'bench_remaining_defrost_20261111.py',kind)
    for kind in ('cool','heat'):add('two_fixed_rotation_'+kind,'bench_remaining_rotation_20261111.py',kind)
    add('all_six_fans300s','bench_remaining_prestart_20261111.py','--minimum-seconds','300')
    add('parameter_boundary_matrix','bench_remaining_adapter_20261111.py','parameters')
    add('manual_contact_protection','bench_remaining_adapter_20261111.py','manual-contacts')
    return plan

def supplemental_tasks():
    return [('NTC0_peer_diagnostic_recheck',['ntc0-diagnostics']),
        ('four_coil_continuity',['coil-continuity']),
        *[(f'vfd_curve_{v}',['vfd-curve','--value',str(v)]) for v in (12,22,24)],
        *[(f'ambient_existing_gaps_{v}',['ambient-history-gaps','--value',str(v)]) for v in (0,1)],
        ('natural_defrost_independent_fin_exit',['natural-defrost-fin-exit']),
        ('emergency_defrost_cleanup',['emergency']),
        ('ordinary_defrost_allocation_exclusion',['allocation']),
        ('current_firmware_uninterrupted2h',['soak'])]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--after-process',type=int)
    parser.add_argument('--phase',choices=('main','supplemental'),default='main');args=parser.parse_args()
    plan=tasks() if args.phase=='main' else supplemental_tasks()
    path=DAY/('current_controller_'+time.strftime('%H%M%S')+'.json')
    log=dict(started=stamp(),status='running',profile='BENCH_ONLY_3S',phase=args.phase,steps=[],
        tasks=[dict(key=k,arguments=a) for k,a in plan],completed=[])
    def save():
        tmp=path.with_suffix('.json.tmp');tmp.write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)
    def call(key,arguments):
        entry=dict(key=key,arguments=arguments,started=stamp());log['steps'].append(entry);save()
        target=DAY/(path.stem+f'_step_{len(log["steps"]):03d}_'+key+'.log')
        with target.open('w',encoding='utf8') as out:
            print('QUEUE START',key,flush=True)
            process=subprocess.Popen([sys.executable,'-X','utf8','-u','tools/bench_current_20261112.py',*arguments],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
            entry.update(pid=process.pid,output=str(target.relative_to(ROOT)));save()
            # Child procedures have bounded acquisition/wait loops and finally
            # recovery. A pause request is checked inside those procedures.
            result=process.wait()
        entry.update(exitcode=result,finished=stamp());save()
        print('QUEUE END',key,result,flush=True);return result
    def audit():
        for attempt in range(3):
            if call('independent_restoration_audit_'+str(attempt),['audit'])==0:return
            time.sleep(2)
        raise RuntimeError('Independent restoration could not be verified; no next stimulus started')
    try:
        save()
        if args.after_process:
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.OpenProcess.restype=ctypes.c_void_p
            kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
            kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            handle=kernel.OpenProcess(0x00100000,False,args.after_process)
            if handle:
                log['waiting_for_predecessor']=args.after_process;save()
                try:
                    while kernel.WaitForSingleObject(handle,1000)==258:pass
                finally:kernel.CloseHandle(handle)
            log['predecessor_finished']=stamp();save()
        audit()
        for key,arguments in plan:
            if PAUSE.exists():log['status']='paused_by_user';break
            call(key,arguments)
            audit()
            log['completed'].append(key);save()
        if log['status']=='running':log['status']='scheduled_batches_finished_review_case_evidence'
    except BaseException as exc:
        log.update(status='restoration_or_controller_error',error=repr(exc));save();raise
    finally:
        log['finished']=stamp();save();print('CONTROLLER EVIDENCE',path,flush=True)

if __name__=='__main__':main()
