// 规格参数一次性对齐（2026-09-14）
//
// 背景：Parameter_def 的默认值只在「恢复出厂设置」时才写进 Parameter[]，
// 正常运行从 EEPROM 加载。设备上的一批参数仍是旧固件的值，与 20260428
// 规格书偏离，且部分已导致功能异常（见每条注释的 spec 出处）。
//
// 做法：仿照已有的 IndoorAIMigrationMarker / IndoorWDSDMigrationMarker，
// 用 Parameter[456] 作一次性标记，只写下面列出的 21 个索引，不做整表复位，
// 因此不会碰掉现场设定值（设定温度、湿度、外机数量、风阀方式等）。
//
// 插入的代码全部为 ASCII（该文件本身是 UTF-8，latin1 字节透明写入）。
export default [
  // 1) User.h —— 新增迁移标记宏与常量
  {
    file: "PSC330RK-V10-内机/User/UserHead/User.h",
    old: "#define INDOOR_WD_SD_MIGRATION_VALUE 341",
    new:
      "#define INDOOR_WD_SD_MIGRATION_VALUE 341\n" +
      "#define IndoorSpecParamMarker     Parameter[456]\n" +
      "#define INDOOR_SPEC_PARAM_MIGRATION_VALUE 356",
    count: 1,
  },

  // 2) user.c / ParameterInit() —— 新标记的默认值（与既有标记同样写法）
  {
    file: "PSC330RK-V10-内机/User/UserSrc/user.c",
    old: "Parameter_def[455]=INDOOR_WD_SD_MIGRATION_VALUE;",
    new:
      "Parameter_def[455]=INDOOR_WD_SD_MIGRATION_VALUE;\n" +
      "\tParameter_max[456]=32767; Parameter_min[456]=0;\tParameter_def[456]=INDOOR_SPEC_PARAM_MIGRATION_VALUE;",
    count: 1,
  },

  // 3) user.c / IndoorMigrateSpecConfiguration() —— 一次性写出规格值
  {
    file: "PSC330RK-V10-内机/User/UserSrc/user.c",
    old:
      "\tif(SupplyFanMinVoltSet > SupplyFanMaxVoltSet)\n" +
      "\t\tSupplyFanMaxVoltSet = SupplyFanMinVoltSet;\n" +
      "}",
    new:
      "\tif(SupplyFanMinVoltSet > SupplyFanMaxVoltSet)\n" +
      "\t\tSupplyFanMaxVoltSet = SupplyFanMinVoltSet;\n" +
      "\t/* Spec parameter alignment. Parameter_def defaults are only applied on\n" +
      "\t   factory reset, so a unit whose EEPROM still holds pre-spec values keeps\n" +
      "\t   them. This one-shot migration writes the spec values for the parameters\n" +
      "\t   found deviating from spec 20260428 that change behaviour. Only the\n" +
      "\t   indices listed here are touched; no blanket reset is performed. */\n" +
      "\tif(IndoorSpecParamMarker != INDOOR_SPEC_PARAM_MIGRATION_VALUE)\n" +
      "\t{\n" +
      "\t\tParameter[MinStopTimeSet] = 120;        /* compressor min stop, s     spec 3.4.2: 2 min */\n" +
      "\t\tParameter[MinValveOpenSet] = 200;       /* winter valve min, 0.1%     spec 3.11.10 */\n" +
      "\t\tParameter[DiskCheckSet] = 5;            /* evap coil hold, min        spec 3.4: 5 min */\n" +
      "\t\tParameter[DiskSet] = 50;                /* evap coil release, 0.1C    spec 3.4: 5.0C */\n" +
      "\t\tParameter[PidAdjustTimeSet1] = 5;       /* PID scan period T, s       spec 3.4: 5 s */\n" +
      "\t\tParameter[IntegralCoeSet1] = 100;       /* TIL, s                     spec 3.4: 100 s */\n" +
      "\t\tParameter[ProportionCoeSet2] = 5;       /* KPR                        spec 3.4: 5 */\n" +
      "\t\tParameter[IntegralCoeSet2] = 100;       /* TIR, s                     spec 3.4: 100 s */\n" +
      "\t\tParameter[DerivativeCoeSet2] = 0;       /* KDR                        spec 3.4: 0 */\n" +
      "\t\tParameter[QHBSet] = 50;                 /* reheat ratio, 0.01         spec 3.5: 0.5 */\n" +
      "\t\tParameter[QHSSet] = 600;                /* auto switch delay, s       spec 3.5: 600 s */\n" +
      "\t\tParameter[ReheatTiSet] = 100;           /* TIRZ, s                    spec 3.6: 100 s */\n" +
      "\t\tParameter[PreheatKpSet] = 5;            /* KPY                        spec 3.7: 5 */\n" +
      "\t\tParameter[PreheatTiSet] = 100;          /* TIY, s                     spec 3.7: 100 s */\n" +
      "\t\tParameter[PreheatTdSet] = 0;            /* KDY                        spec 3.7: 0 */\n" +
      "\t\tParameter[PreheatStartTempSet] = 0;     /* preheat start, 0.1C        spec 3.7: 0C */\n" +
      "\t\tParameter[PreheatFullLoadTempSet] = -50;/* preheat full load, 0.1C    spec 3.7: -5C */\n" +
      "\t\tParameter[PreheatAfterTempSet] = 50;    /* YWD, 0.1C                  spec 3.7: 5C */\n" +
      "\t\tParameter[HumidTiSet] = 100;            /* TIS, s                     spec 3.8: 100 s */\n" +
      "\t\tParameter[VentilationFanVoltSet] = 80;  /* vent fan voltage, 0.1V     spec 3.10: 8V */\n" +
      "\t\tParameter[AirVolumeSet] = 1000;         /* air volume, 10 CMH         spec 3.10: 10000 CMH */\n" +
      "\t\tIndoorSpecParamMarker = INDOOR_SPEC_PARAM_MIGRATION_VALUE;\n" +
      "\t}\n" +
      "}",
    count: 1,
  },
];
