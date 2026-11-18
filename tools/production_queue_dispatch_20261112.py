"""One formal-profile action, followed by independent normal-stop audit."""
import production_queue_context_20261112 as context
import argparse
import sys

def main():
    if sys.argv[1:]==['final-audit']:
        q=context.audit('T17_002_formal_final_full_image',True)
        c=context.runtime.client()
        try:
            values={str(a):c.read_holding_registers(1,a,1)[0] for a in (42,43,398,709,1298,1299)}
            assert values['42']>=120 and values['43']>=180 and values['1298']==300
            assert values['398']==values['709']==values['1299']==0
            context.dump(context.DAY/'T17_002_final_profile.json',dict(at=context.now(),settings=values,
                verified_software_scope=True,physical_power_cycle_test=False,
                note='Three PRODUCTION images fully read back, restored configuration and formal minima; physical restart remains separate'))
        finally:c.close()
        return
    if sys.argv[1:]==['audit']:
        context.audit();return
    if sys.argv[1:]==['soak']:
        import continuous_followups_v1055_20261109 as test
        test.D=context.DAY;test.CheckedBench=context.ProductionBench;test.BOARDS=context.BOARDS
        test.soak();context.audit('after_formal_two_hour_audit');return
    import production_queue_cases_20261112 as test
    p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('--mode',type=int,default=2)
    p.add_argument('--valves',action='store_true');p.add_argument('--exhaust',type=int,default=0)
    p.add_argument('--return-delay',type=int,default=0);p.add_argument('--return-present',action='store_true')
    p.add_argument('--humidifier',action='store_true');p.add_argument('--ids',nargs='*',default=[]);a=p.parse_args()
    if a.action=='sequence':test.run_sequence(a.mode,a.valves,a.exhaust,a.return_delay,a.return_present,a.ids)
    elif a.action=='loaded':test.run_loaded(a.humidifier,a.mode)
    elif a.action=='fourway':test.run_fourway()
    elif a.action=='fan15':test.run_fan15()
    elif a.action=='ambient':
        import production_queue_ambient_20261112 as ambient
        ambient.run()
    else:raise ValueError(a.action)
    context.audit('after_'+a.action+'_formal_audit')

if __name__=='__main__':main()
