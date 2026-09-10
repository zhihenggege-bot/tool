export default [
  {
    file: "D:/Companty/WEll thinker/F/code/PSC330RK-V10-内机/User/UserSrc/user.c",
    old: `static void IndoorMigrateSpecConfiguration(void)
{
\tif(PressureProtectEnableSet < 2)
\t{
\t\tunsigned int installed = PressureProtectEnableSet ? 1 : 0;
\t\tunsigned char eepromData[10];
\t\tunsigned int i;
\t\tunsigned int eepromMatches = 1;`,
    new: `static void IndoorMigrateSpecConfiguration(void)
{
\tunsigned int i;
\tint16_t oldCalibration[13];
\tif(PressureProtectEnableSet < 2)
\t{
\t\tunsigned int installed = PressureProtectEnableSet ? 1 : 0;
\t\tunsigned char eepromData[10];
\t\tunsigned int eepromMatches = 1;`,
  },
  {
    file: "D:/Companty/WEll thinker/F/code/PSC330RK-V10-内机/User/UserSrc/user.c",
    old: `\t}
\tif(CoolHeatFanVoltSet < 50)CoolHeatFanVoltSet = 50;
\tif(SupplyFanMaxVoltSet < 50)SupplyFanMaxVoltSet = 50;
\tif(SupplyFanMinVoltSet > SupplyFanMaxVoltSet)
\t\tSupplyFanMaxVoltSet = SupplyFanMinVoltSet;
}

/**************void User(void)***************/`,
    new: `\t}
\tif(IndoorAIMigrationMarker != INDOOR_AI_MIGRATION_VALUE)
\t{
\t\tfor(i=0; i<13; i++)
\t\t\toldCalibration[i] = Parameter[495-i];
\t\tIndoorAI4CalibrationSet = oldCalibration[0];
\t\tfor(i=0; i<12; i++)
\t\t\tParameter[495-i] = oldCalibration[i+1];
\t\tIndoorAIEnableMaskLowSet = INDOOR_AI_ENABLE_LOW_MASK;
\t\tIndoorAIEnableMaskHighSet = INDOOR_AI_ENABLE_HIGH_MASK;
\t\tIndoorAIMigrationMarker = INDOOR_AI_MIGRATION_VALUE;
\t}
\tIndoorAIEnableMaskLowSet &= INDOOR_AI_ENABLE_LOW_MASK;
\tIndoorAIEnableMaskHighSet &= INDOOR_AI_ENABLE_HIGH_MASK;
\tfor(i=484; i<=499; i++)
\t{
\t\tif(Parameter[i] > AI_CALIBRATION_LIMIT)Parameter[i] = AI_CALIBRATION_LIMIT;
\t\tif(Parameter[i] < -AI_CALIBRATION_LIMIT)Parameter[i] = -AI_CALIBRATION_LIMIT;
\t}
\tif(IndoorAI4CalibrationSet > AI_CALIBRATION_LIMIT)
\t\tIndoorAI4CalibrationSet = AI_CALIBRATION_LIMIT;
\tif(IndoorAI4CalibrationSet < -AI_CALIBRATION_LIMIT)
\t\tIndoorAI4CalibrationSet = -AI_CALIBRATION_LIMIT;
\tif(CoolHeatFanVoltSet < 50)CoolHeatFanVoltSet = 50;
\tif(SupplyFanMaxVoltSet < 50)SupplyFanMaxVoltSet = 50;
\tif(SupplyFanMinVoltSet > SupplyFanMaxVoltSet)
\t\tSupplyFanMaxVoltSet = SupplyFanMinVoltSet;
}

unsigned char IndoorAIEnabled(unsigned int channel)
{
\tif(channel < 8)
\t\treturn (IndoorAIEnableMaskLowSet & (1U << channel)) ? 1 : 0;
\tif(channel < 17)
\t\treturn (IndoorAIEnableMaskHighSet & (1U << (channel-8))) ? 1 : 0;
\treturn 0;
}

/**************void User(void)***************/`,
  },
  {
    file: "D:/Companty/WEll thinker/F/code/PSC330RK-V10-内机/User/NTC16bit/NTC16bit.c",
    old: `\tfloat vol,res,Tmantissa;
\tfloat Tempbuf[NTCNum];
\tuint8_t j;`,
    new: `\tfloat vol,res,Tmantissa;
\tfloat Tempbuf[NTCNum];
\tint16_t calibration;
\tuint8_t j;`,
  },
  {
    file: "D:/Companty/WEll thinker/F/code/PSC330RK-V10-内机/User/NTC16bit/NTC16bit.c",
    old: `\t\t\tTempbuf[i] = (float)Indx + Tmantissa;
\t\t\t
\t\t\tNTC[i] = round(Tempbuf[i]*10)+Parameter[ParameterSaveSize-5-i];//`,
    new: `\t\t\tTempbuf[i] = (float)Indx + Tmantissa;

\t\t\tswitch(i)
\t\t\t{
\t\t\t\tcase 0: calibration = UserA5ValueSet; break;
\t\t\t\tcase 1: calibration = UserA6ValueSet; break;
\t\t\t\tcase 2: calibration = UserA7ValueSet; break;
\t\t\t\tcase 3: calibration = UserA8ValueSet; break;
\t\t\t\tcase 4: calibration = UserA9ValueSet; break;
\t\t\t\tcase 5: calibration = UserA10ValueSet; break;
\t\t\t\tcase 6: calibration = UserA11ValueSet; break;
\t\t\t\tcase 7: calibration = UserA12ValueSet; break;
\t\t\t\tcase 8: calibration = UserA13ValueSet; break;
\t\t\t\tcase 9: calibration = UserA14ValueSet; break;
\t\t\t\tcase 10: calibration = UserA15ValueSet; break;
\t\t\t\tdefault: calibration = UserA16ValueSet; break;
\t\t\t}
\t\t\tNTC[i] = round(Tempbuf[i]*10)+calibration;//`,
  },
];
