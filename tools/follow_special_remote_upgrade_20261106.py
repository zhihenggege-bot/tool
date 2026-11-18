"""Keep one hardware writer: old queue -> recovery -> 330 update -> regression."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
PREVIOUS=ROOT/'测试证据/内机实测_20261105/BENCH_V1053_V1239/live_queue_20261106_124455.json'
JOURNAL=ROOT/'.codex-tmp/special_remote_upgrade_followup_20261106.json'


def main():
    log=dict(started_epoch=time.time(),stage='waiting_predecessor',hardware_opened=False)
    def save():JOURNAL.write_text(json.dumps(log,indent=2),'utf8')
    save();last_report=0
    while True:
        try:previous=json.loads(PREVIOUS.read_text('utf8'))
        except json.JSONDecodeError:time.sleep(.2);continue
        assert not previous.get('blocked_reason'),previous.get('blocked_reason')
        if previous.get('finished_epoch'):
            assert previous.get('running') is None
            assert len(previous['batches'])==len(previous['actions'])
            assert all(b.get('recovered') is True for b in previous['batches'])
            break
        if time.monotonic()-last_report>=60:
            print('WAIT PREDECESSOR',previous.get('running'),flush=True);last_report=time.monotonic()
        time.sleep(1)
    log['stage']='independent_readback_old_image';save()
    old=ROOT/'测试证据/内机实测_20261105/BENCH_V1053_V1239/heat_final_independent_readback_20261106.json'
    if old.exists():
        backup=old.with_name('heat_final_independent_readback_before_upgrade_'+time.strftime('%H%M%S')+'.json')
        backup.write_bytes(old.read_bytes())
    subprocess.run([sys.executable,'-u',str(ROOT/'tools/check_heat_final_board_20261106.py')],cwd=ROOT,check=True)
    log['stage']='flash330_v1054';log['hardware_opened']=True;save()
    subprocess.run([sys.executable,'-u',str(ROOT/'tools/flash_special_remote_v1054_20261106.py')],cwd=ROOT,check=True)
    log['stage']='v1054_regression';save()
    env=dict(os.environ,PSC_BENCH_PACKAGE='.codex-tmp/special_remote_v1054_v1239_20261106',PSC_BENCH_INDOOR_VERSION='10.54')
    subprocess.run([sys.executable,'-u',str(ROOT/'tools/continue_live_queue_20261106.py'),
        'remote-regression','fan-enums','extra-di','loaded-modes','mode-transitions','eev-startups'],cwd=ROOT,env=env,check=True)
    log.update(stage='finished',finished_epoch=time.time());save()
    print('UPGRADE AND FOLLOWUP COMPLETE',flush=True)


if __name__=='__main__':main()
