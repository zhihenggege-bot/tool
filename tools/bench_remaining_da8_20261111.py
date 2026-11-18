"""Observe existing DA8 manual selector; do not invent a medium-enable enum."""
from bench_remaining_outdoor_20261111 import *
from continuous_followups_v1055_20261109 import cold_config


def main():
    b=current_bench_class()('remaining_indoor_DA8_selection')
    e=b.log['remaining_functional']=dict(kind='indoor_DA8_existing_selector',cases=[],
        scope='Ordinary330[245]/[247] selector and command; softwareDA8 only. No separate cold-water medium enable is defined/claimed; observe existing behavior without changing its permission rule')
    try:
        cold_config(b,2);b.config({245:1,247:0});b.start()
        for value in (0,500,0):
            b.config({247:value});row=dict(id='T06-025',label='existing_DA8_manual_'+str(value),samples=[])
            e['cases'].append(row);began=time.monotonic()
            while time.monotonic()-began<5:
                s=b.snapshot('existing DA8 input');s.update(selector245=b.rd(245)[0],input247=b.rd(247)[0],display925=b.rd(925)[0])
                row['samples'].append(s);time.sleep(.15)
            row.update(final=s,finished=now(),observed_matches_command=s['ao'][8]==value)
            # Permission by medium is unresolved. Record a trace, not a full
            # acceptance pass or an invented unsupported selector.
            b.save();print('DA8 EXISTING SELECTOR',value,s['ao'][8],flush=True)
        b.stop();row=dict(id='T06-025',label='existing_DA8_stopped',samples=b.observe('DA8 stopped hold',4))
        row.update(final=row['samples'][-1],finished=now());e['cases'].append(row)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':main()
