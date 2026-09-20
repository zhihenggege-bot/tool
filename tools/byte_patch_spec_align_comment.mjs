// 把规格对齐迁移的注释补全（说明设计取舍，供后人阅读）
export default [
  {
    file: "PSC330RK-V10-内机/User/UserSrc/user.c",
    old:
      "\t/* Spec parameter alignment. Parameter_def defaults are only applied on\n" +
      "\t   factory reset, so a unit whose EEPROM still holds pre-spec values keeps\n" +
      "\t   them. This one-shot migration writes the spec values for the parameters\n" +
      "\t   found deviating from spec 20260428 that change behaviour. Only the\n" +
      "\t   indices listed here are touched; no blanket reset is performed. */\n",
    new:
      "\t/* Spec parameter alignment (spec 20260428).\n" +
      "\t *\n" +
      "\t * Why a runtime migration instead of only fixing Parameter_def:\n" +
      "\t * the default tables are written into Parameter[] only on factory reset,\n" +
      "\t * or when the EEPROM has no value yet. A unit that is already running\n" +
      "\t * keeps whatever its EEPROM holds, so the defaults can be fully\n" +
      "\t * spec-correct while the unit still runs pre-spec values -- which is\n" +
      "\t * exactly the state these units were found in (e.g. Parameter_def[110]\n" +
      "\t * is 5 while the unit read 15).\n" +
      "\t *\n" +
      "\t * Marker semantics: Parameter_def[456] is set to the same value as the\n" +
      "\t * marker checked below, so a factory-fresh unit starts with the marker\n" +
      "\t * already set and skips this block. That is correct, because its values\n" +
      "\t * came from the defaults, which are already spec-correct. Only a unit\n" +
      "\t * still carrying stale EEPROM values runs the block. A factory reset\n" +
      "\t * likewise lands on the correct values without running it, so all three\n" +
      "\t * paths (new unit / existing unit / after factory reset) converge on the\n" +
      "\t * same result.\n" +
      "\t *\n" +
      "\t * Scope: only the indices listed below are written. Site settings\n" +
      "\t * (setpoints, humidity, outdoor unit count, valve and fan output modes,\n" +
      "\t * AI calibration) are deliberately left untouched -- there is no blanket\n" +
      "\t * reset, and the block runs once so the field can still retune later.\n" +
      "\t *\n" +
      "\t * Every value below lies inside Parameter_min/max, so the start-up table\n" +
      "\t * consistency check does not reject it. */\n",
    count: 1,
  },
];
