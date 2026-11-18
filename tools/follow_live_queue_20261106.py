"""Start a follow-up only after the preceding serial queue records recovery."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('predecessor',type=Path)
    p.add_argument('actions',nargs='+')
    args=p.parse_args()
    previous=ROOT/args.predecessor
    print('WAIT FOR RECOVERED QUEUE',previous,flush=True)
    last_report=0
    while True:
        try:data=json.loads(previous.read_text('utf8'))
        except json.JSONDecodeError:
            time.sleep(.2);continue
        if data.get('blocked_reason'):
            raise RuntimeError(('predecessor restoration not confirmed',data['blocked_reason']))
        if data.get('finished_epoch'):
            assert data.get('running') is None,data
            assert len(data['batches'])==len(data['actions']),data
            assert all(b.get('recovered') is True for b in data['batches']),data
            break
        if time.monotonic()-last_report>=60:
            print('WAITING predecessor action',data.get('running'),flush=True)
            last_report=time.monotonic()
        time.sleep(1)
    print('PREDECESSOR RECOVERED; START FOLLOW-UP',args.actions,flush=True)
    result=subprocess.run([sys.executable,'-u',str(ROOT/'tools/continue_live_queue_20261106.py'),*args.actions],cwd=ROOT)
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
