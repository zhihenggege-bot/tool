"""Deploy330 V10.63 only; two316 images remain byte-for-byte V12.44."""
import manual_delivery_fix_context_20261113 as ctx
import deploy_reset_retrigger_v1062_20261113 as deploy
import traceback
import time

deploy.ctx=ctx;deploy.g=ctx.g
deploy.OLD=ctx.R/'.codex-tmp/manual_gate_v1062_v1244_20261113/BENCH_ONLY_3S'
deploy.EXPECTED_BEFORE=[330,10,62,2026,11,13,316,12,44,2026,11,13,316,12,44,2026,11,13]
deploy.ARM_FILE='reset_delivery_ARM_regression.json'

if __name__=='__main__':
    try:deploy.main()
    except BaseException:
        ctx.g.dump(ctx.DAY/('deployment_error_'+time.strftime('%H%M%S')+'.json'),dict(at=ctx.g.now(),error=traceback.format_exc()));raise
