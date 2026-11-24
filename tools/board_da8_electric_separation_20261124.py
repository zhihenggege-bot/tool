"""Board check with electrical AO configured and no heating capacity requested."""
import traceback
import board_da8_manual_v1074_20261124 as test


class Bench(test.Bench):
    record_name='board_electric_separation'


def main():
    b=Bench()
    try:
        b.temperature(0,250);b.temperature(1,250);b.temperature(2,-1)
        b.config({163:0,164:0,165:0,236:1,125:0,126:0,128:2,127:1,129:1,
            332:1,333:1,334:0,335:0,336:0,337:0,338:0,315:0,320:0,248:0,
            161:150,247:0,346:200,356:-100,357:-200,374:0})
        b.wr(398,1)
        for heat_mode,share in ((2,1),(1,1),(1,0)):
            b.config({128:heat_mode,129:share})
            row=b.row(f'configured electric AO heat{heat_mode} share{share}: water200, electric0 under zero demand')
            b.wait(row,lambda z:z['step']==2 and z['mode']==1 and z['fresh10']==-1
                and z['room10']==250 and b.output(z,200)
                and all(z['da'][i]==0 for i in (0,1,9)),timeout=155,hold=8)
        b.log['sequence_completed']=True;b.save()
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:b.finish()
    b.log['passed']=all(row['passed'] for row in b.log['cases']) and b.log.get('restored',False)
    b.save();assert b.log['passed']
    print('BOARD ELECTRIC FROST SEPARATION PASS',flush=True)


if __name__=='__main__':main()
