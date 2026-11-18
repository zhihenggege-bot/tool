"""Serial test queue. Each selected batch owns recovery before the next opens COM6."""
import os
os.environ.setdefault('PSC_BENCH_PACKAGE', '.codex-tmp/preheat_stage_display_v1053_v1239_20261106')
os.environ.setdefault('PSC_BENCH_INDOOR_VERSION', '10.53')
import argparse
import importlib
import json
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_major,_minor=map(int,os.environ['PSC_BENCH_INDOOR_VERSION'].split('.'))
BASE = ROOT / f'测试证据/内机实测_20261105/BENCH_V{_major}{_minor:02d}_V1239'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('actions', nargs='+')
    args = p.parse_args()
    queue = {'started_epoch': time.time(), 'batches': [], 'actions': args.actions}
    path = BASE / ('live_queue_' + time.strftime('%Y%m%d_%H%M%S') + '.json')
    def save(): path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), 'utf8')
    for action in args.actions:
        item = {'action': action, 'started_epoch': time.time()}
        queue['batches'].append(item)
        queue['running'] = action
        save()
        print('QUEUE START', action, flush=True)
        before = set(BASE.glob('remaining571_heat_dynamic_*.json'))
        try:
            if action.startswith('exact:'):
                importlib.import_module('remaining_pid_exact_live_20261106').run_exact(action.split(':')[1])
            elif action == 'auto-humidity':
                importlib.import_module('remaining_auto_humidity_live_20261106').main()
            elif action == 'eev':
                importlib.import_module('remaining_eev_live_20261106').main()
            elif action == 'eev-midpoints':
                importlib.import_module('remaining_eev_live_20261106').main(midpoints=True)
            elif action == 'eev-startups':
                importlib.import_module('remaining_eev_live_20261106').main(startups=True)
            elif action == 'di-protections':
                importlib.import_module('remaining_di_protection_live_20261106').main()
            elif action == 'special-di-protections':
                importlib.import_module('remaining_di_protection_live_20261106').main(modes=(3,4,5))
            elif action == 'remote-regression':
                importlib.import_module('remaining_di_protection_live_20261106').main(modes=(0,1,2,3,4,5),kinds=('remote',))
            elif action == 'fan-enums':
                importlib.import_module('remaining_compatibility_live_20261106').fan_enums()
            elif action == 'extra-di':
                importlib.import_module('remaining_compatibility_live_20261106').extra_di()
            elif action == 'loaded-modes':
                importlib.import_module('remaining_loaded_modes_live_20261106').main()
            elif action == 'mode-transitions':
                importlib.import_module('remaining_mode_transitions_live_20261106').main()
            elif action == 'ambient-preheat':
                importlib.import_module('remaining_pid_boundaries_live_20261106').ambient_preheat()
            elif action == 'mode-permissions':
                importlib.import_module('remaining_mode_permissions_live_20261106').main()
            elif action.startswith('auto-long:'):
                importlib.import_module('remaining_auto_long_qhs_live_20261106').main(int(action.split(':')[1]))
            else: raise ValueError(action)
            item['completed'] = True
        except Exception:
            item['error'] = traceback.format_exc()
            print(item['error'], flush=True)
        fresh = sorted(set(BASE.glob('remaining571_heat_dynamic_*.json')) - before)
        item['evidence'] = [p.relative_to(ROOT).as_posix() for p in fresh]
        recovered=[]
        for evidence in fresh:
            data=json.loads(evidence.read_text('utf8'))
            recovered.append(data.get('restored') is True and
                all(data.get('outdoor_configuration_restored',{}).values()) and
                not data.get('cleanup_error'))
        item['recovered'] = bool(fresh) and all(recovered)
        item['finished_epoch'] = time.time()
        save()
        print('QUEUE FINISHED', action, 'completed', item.get('completed', False), 'restored', item['recovered'], flush=True)
        if not item['recovered']:
            queue['blocked_reason'] = 'Recovery not confirmed; do not start another hardware writer'
            save()
            raise RuntimeError(queue['blocked_reason'])
    queue['running'] = None
    queue['finished_epoch'] = time.time()
    save()
    print('QUEUE DONE', path, flush=True)


if __name__ == '__main__': main()
