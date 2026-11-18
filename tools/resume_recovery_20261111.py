"""Recover the interrupted case through ordinary stop/configuration inputs."""
from joint_v1058_context_20261111 import *
import json


def run():
    source=DAY/'outdoor_running_disable_115446.json'
    prior=json.loads(source.read_text('utf8'))
    b=current_bench_class()('resume_interrupted_recovery')
    b._cleaning_up=True
    b.log['interrupted_journal']=source.relative_to(ROOT).as_posix()
    # Restore from the pre-interruption snapshot, never from today's dirty state.
    b.original.update(prior['original'])
    b.touched.update(map(int,prior['original']))
    b.gateway_original.update({int(a):v for a,v in prior['gateway_original'].items()})
    b.save()
    b.finish()
    assert b.log.get('restored') and all(b.log.get('gateway_restored',{}).values())
    print('RECOVERY COMPLETE',b.path,flush=True)


if __name__=='__main__':run()
