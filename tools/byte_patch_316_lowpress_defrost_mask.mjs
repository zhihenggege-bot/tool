// PSC316 外机：恢复「化霜时屏蔽低压开关」（规格书 4.4.3）
//
// 规格书 4.4.3 明文要求：
//   「化霜开始：向室内机发出化霜开始指令，屏蔽低压开关，室外机风机关，
//     四通阀失电，所有压缩机开（已经开启的压缩机不关闭，未开启的压缩机
//     间隔30秒开）（故障压缩机除外）。」
//
// 代码现状（HEAD）：低压检测调用位于 if(InDefrost)/else 块【之外】，化霜期间
// 无条件执行；而化霜时压缩机全开、四通阀失电（=制冷回路）、室外风机停，
// 低压侧压力下降，低压开关跳开 5 秒即置 CompLowPress1/2Err 并停系统，
// 导致化霜被误中断。
//
// 历史：commit 5f86e9a（26.0911-A）删除了整套化霜屏蔽机制，包括辅助函数
// InOutdoorDefrost()/OutdoorLowPressureMaskedByDefrost()、局部变量 LowPressMasked、
// 化霜时对低压计数的清零，以及两次调用上的 `&& EnableCheckLow[n]` 门控。
// EnableCheckLow[] 由 DefAction.c 在化霜期间置 0，正是「化霜中」的语义，
// 现在已成为死变量（只在 DefAction.c 写、无人读）。
//
// 本补丁按老设计恢复：化霜期间整条调用跳过，并把低压计数清零；已锁存的故障
// 保持不变（不因化霜而被解除），与 5f86e9a 之前的行为一致。
//
// 注意：ErrorCheck.c 是 GBK 编码，必须字节级改（本工具用 latin1 透明读写）；
// 插入的代码全为 ASCII。
export default [
  {
    file: "PSC316RK-V12-外机/WELLTHINKER/User/ErrorCheck.c",
    old:
      "\t/* Low pressure is checked for five seconds whenever the compressor is actually running. */\n" +
      "\tOutdoorLowPress5sCheck(0,\n" +
      "\t\t(Comp1Y05\n" +
      "\t\t&&(((LowPressDisp1 < LowPressWarn)&&(SensorErr[2]==0)&&((PressSensor==1)||(PressSensor==2))) || Comp1LowX01)),\n" +
      "\t\t((Comp1LowX01==0)&&(SensorErr[2]==0)&&(LowPressDisp1>=LowPressWarn)),\n" +
      "\t\tLowPressCount);\n" +
      "\n" +
      "\tOutdoorLowPress5sCheck(1,\n" +
      "\t\t(Comp2Y06\n" +
      "\t\t&&(((LowPressDisp2 < LowPressWarn)&&(SensorErr[3]==0)&&((PressSensor==1)||(PressSensor==2))) || Comp2LowX03)),\n" +
      "\t\t((Comp2LowX03==0)&&(SensorErr[3]==0)&&(LowPressDisp2>=LowPressWarn)),\n" +
      "\t\tLowPressCount);\n",
    new:
      "\t/* Low pressure is checked for five seconds whenever the compressor is actually running.\n" +
      "\t   Spec 4.4.3 masks the low-pressure switch while defrosting, so the check is skipped for\n" +
      "\t   the whole defrost cycle and a latched fault is left untouched. This restores the\n" +
      "\t   pre-26.0911-A behaviour, whose defrost gate was dropped in commit 5f86e9a. */\n" +
      "\tif(InDefrost)\n" +
      "\t{\n" +
      "\t\tLowPressCount[0]=0; LowPressCount[1]=0;\n" +
      "\t}\n" +
      "\telse\n" +
      "\t{\n" +
      "\t\tOutdoorLowPress5sCheck(0,\n" +
      "\t\t\t(Comp1Y05\n" +
      "\t\t\t&&(((LowPressDisp1 < LowPressWarn)&&(SensorErr[2]==0)&&((PressSensor==1)||(PressSensor==2))) || Comp1LowX01)),\n" +
      "\t\t\t((Comp1LowX01==0)&&(SensorErr[2]==0)&&(LowPressDisp1>=LowPressWarn)),\n" +
      "\t\t\tLowPressCount);\n" +
      "\n" +
      "\t\tOutdoorLowPress5sCheck(1,\n" +
      "\t\t\t(Comp2Y06\n" +
      "\t\t\t&&(((LowPressDisp2 < LowPressWarn)&&(SensorErr[3]==0)&&((PressSensor==1)||(PressSensor==2))) || Comp2LowX03)),\n" +
      "\t\t\t((Comp2LowX03==0)&&(SensorErr[3]==0)&&(LowPressDisp2>=LowPressWarn)),\n" +
      "\t\t\tLowPressCount);\n" +
      "\t}\n",
    count: 1,
  },
];
