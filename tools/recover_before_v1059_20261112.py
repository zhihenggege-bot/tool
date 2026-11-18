"""Recover the exact interrupted V10.58 bench journal before upgrading."""
import json
from pathlib import Path
import joint_v1058_context_20261111 as ctx

def main():
    day = ctx.ROOT / '测试证据/台架执行_20261112'
    ctx.runtime.D = day
    ctx.DAY = day
    source = ctx.ROOT / '测试证据/台架执行_20261111/remaining_heat_dispatch_4_184536.json'
    prior = json.loads(source.read_text('utf8'))
    assert prior.get('original')
    b = ctx.current_bench_class()('recover_interrupted_v1058')
    b._cleaning_up = True
    b.log['interrupted_journal'] = source.relative_to(ctx.ROOT).as_posix()
    b.original.update(prior['original'])
    b.touched.update(map(int, prior['original']))
    b.gateway_original.update({int(a): v for a,v in prior.get('gateway_original', {}).items()})
    b.save()
    b.finish()
    assert b.log.get('restored') and all(b.log.get('gateway_restored', {}).values())
    print('RECOVERY VERIFIED', b.path, flush=True)

if __name__ == '__main__':
    main()
