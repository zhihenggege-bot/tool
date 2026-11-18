"""Restore an exact interrupted batch snapshot through normal HMI commands."""
from joint_v1058_context_20261111 import *
import argparse


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);args=parser.parse_args()
    source=(ROOT/args.source).resolve();assert source.is_relative_to(DAY.resolve())
    prior=json.loads(source.read_text('utf8'));assert prior.get('original')
    b=current_bench_class()('recover_exact_queue_journal');b._cleaning_up=True
    b.log['interrupted_journal']=source.relative_to(ROOT).as_posix()
    b.original.update(prior['original']);b.touched.update(map(int,prior['original']))
    b.gateway_original.update({int(a):v for a,v in prior.get('gateway_original',{}).items()})
    raw_write=b.c.write_single_register

    def retry_write(slave,address,value):
        for attempt in range(4):
            try:return raw_write(slave,address,value)
            except Exception as exc:
                b.log.setdefault('restoration_write_retries',[]).append(dict(at=now(),address=address,
                    value=value,attempt=attempt,error=repr(exc)));b.save()
                if attempt==3:raise
                time.sleep(.4)
                try:
                    if b.c.read_holding_registers(slave,address,1)==[value&65535]:return
                except Exception:pass
    b.c.write_single_register=retry_write;b.save();b.finish()
    assert b.log.get('restored') and all(b.log.get('gateway_restored',{}).values())
    print('EXACT JOURNAL RECOVERY',b.path,flush=True)


if __name__=='__main__':main()
