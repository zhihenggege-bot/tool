"""Same real2h ventilation windows, with all three board uptimes observed."""
import production_queue_context_20261113 as context

def run():
    import continuous_followups_v1055_20261109 as test
    test.D=context.DAY;test.CheckedBench=context.ProductionBench;test.BOARDS=context.BOARDS
    replacements=[
        ('session=None', 'session=None;outdoor_session=None;previous_outdoor_uptime={}'),
        ('session.open();target=session.target', '''session.open();target=session.target
        from joint_precondition_20261110 import symbols
        outdoor_symbols=[symbols(board) for board in BOARDS[:2]]
        outdoor_session=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[1][1],target_override=BOARDS[1][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        outdoor_session.open()
        outdoor_targets=[b.ot,outdoor_session.target]'''),
        ("uptime=target.read32(b.sy['Systick_1ms'][0]);s['uptime_low32']=uptime", '''uptime=target.read32(b.sy['Systick_1ms'][0]);s['uptime_low32']=uptime
                    s['outdoor_uptime_low32']=[]
                    for index,(outdoor_target,sy) in enumerate(zip(outdoor_targets,outdoor_symbols)):
                        tick=outdoor_target.read32(sy['Systick_1ms'][0])
                        if index in previous_outdoor_uptime:
                            assert (tick-previous_outdoor_uptime[index])&0xffffffff<10000,('outdoor reset/long sampling gap',index+1,previous_outdoor_uptime[index],tick)
                        previous_outdoor_uptime[index]=tick
                        s['outdoor_uptime_low32'].append(tick)'''),
        ('if session:session.close()', 'if outdoor_session:outdoor_session.close()\n        if session:session.close()'),
        ('只读系统运行时钟','330及两台316只读运行时钟')]
    driver=context.adapt(test.soak,replacements,'current_three_board_two_hour_soak')
    driver()

if __name__=='__main__':run()
