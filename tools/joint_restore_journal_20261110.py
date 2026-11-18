"""Recover ordinary settings from an interrupted today's journal, no state pokes."""
from joint_precondition_20261110 import *
import argparse

def main():
    a=argparse.ArgumentParser();a.add_argument('journal',type=Path);args=a.parse_args()
    prior=json.loads(args.journal.read_text('utf8'));dest=DAY/('independent_restore_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),source=str(args.journal),samples=[],writes=[]);c=runtime.client()
    try:
        c.write_single_register(1,398,0);began=time.monotonic()
        while True:
            s=runtime.snap(c);q['samples'].append(s);dump(dest,q)
            if s['state'][9]==0 and loads_off(s):break
            assert time.monotonic()-began<180,('stop incomplete',s);time.sleep(1)
        for key,v in sorted(prior['original'].items(),key=lambda x:int(x[0])):
            addr=int(key)
            if addr in (1,236,398,524):continue
            if c.read_holding_registers(1,addr,1)[0]!=v:
                c.write_single_register(1,addr,v);q['writes'].append(dict(address=addr,value=v));dump(dest,q)
        c.write_single_register(1,236,prior['original']['236']);time.sleep(2)
        c.write_single_register(1,524,1);time.sleep(.3);c.write_single_register(1,524,0);time.sleep(2)
        q['mismatches']={k:[v,c.read_holding_registers(1,int(k),1)[0]] for k,v in prior['original'].items() if int(k) not in (1,398,524) and c.read_holding_registers(1,int(k),1)[0]!=v}
        q['final']=runtime.snap(c);q['restored']=not q['mismatches'] and loads_off(q['final']) and q['final']['state'][9]==0
        q['finished']=now();dump(dest,q);assert q['restored'],q
        print('INDEPENDENT RESTORED',dest,flush=True)
    except BaseException:q['error']=traceback.format_exc();dump(dest,q);raise
    finally:c.close()

if __name__=='__main__':main()
