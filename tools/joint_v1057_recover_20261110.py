"""Normal stop/configuration recovery, including shared sources and gateways."""
from joint_v1057_context_20261110 import *
import sys
CurrentBench=current_bench_class()

def main():
    source=Path(sys.argv[1]);prior=json.loads(source.read_text('utf8'))
    b=CurrentBench('independent_recovery')
    b.path=DAY/('independent_restore_'+time.strftime('%H%M%S')+'.json')
    b.log.update(source=str(source),purpose='Restore interrupted test settings through normal input paths; original test evidence is untouched')
    try:
        b.stop()
        b.config({int(a):v for a,v in prior['original'].items() if int(a) not in (1,398,524)})
        for a,v in prior.get('gateway_original',{}).items():b.gateway_original[int(a)]=v
        # Use the original pre-test values at final cleanup, not the interrupted
        # state's values captured when this recovery object was constructed.
        b.original.update(prior['original']);b.save()
        for a,v in list(b.gateway_original.items()):b.gateway(a,v)
    except BaseException:b.log['recovery_error']=traceback.format_exc();b.save();raise
    finally:b.finish();print('INDEPENDENT RECOVERY',b.path,flush=True)

if __name__=='__main__':main()
