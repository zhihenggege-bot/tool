// 修正规格参数对齐迁移的标记设计缺陷（2026-09-14 现场实测发现）
//
// 缺陷：原实现把标记的【默认值】设成了"已完成"值（356）。而设备上 [456]
// 这个槽从未被写过，EEPROM 空值会回退到默认值 —— 于是"从未迁移过的机器"
// 看起来像"已经迁移过"，迁移被跳过，21 项参数一个都没改。
//
// 修正：标记默认值改为 0（= 未迁移），并把标记值改为 357（避免与已被写入
// 设备内存的 356 撞车）。迁移在新机上多跑一次是无害的（要写的值就等于默认
// 值），因此不需要"新机跳过"语义。
export default [
  // 1) 标记值 356 -> 357
  {
    file: "PSC330RK-V10-内机/User/UserHead/User.h",
    old: "#define INDOOR_SPEC_PARAM_MIGRATION_VALUE 356",
    new: "#define INDOOR_SPEC_PARAM_MIGRATION_VALUE 357",
    count: 1,
  },

  // 2) 标记的默认值改为 0（未迁移），而不是"已完成"值
  {
    file: "PSC330RK-V10-内机/User/UserSrc/user.c",
    old: "\tParameter_max[456]=32767; Parameter_min[456]=0;\tParameter_def[456]=INDOOR_SPEC_PARAM_MIGRATION_VALUE;",
    new: "\tParameter_max[456]=32767; Parameter_min[456]=0;\tParameter_def[456]=0; /* 0 = not migrated yet; see IndoorMigrateSpecConfiguration */",
    count: 1,
  },

  // 3) 注释同步更正：说明标记默认值必须是"未迁移"状态
  {
    file: "PSC330RK-V10-内机/User/UserSrc/user.c",
    old:
      "\t * Marker semantics: Parameter_def[456] is set to the same value as the\n" +
      "\t * marker checked below, so a factory-fresh unit starts with the marker\n" +
      "\t * already set and skips this block. That is correct, because its values\n" +
      "\t * came from the defaults, which are already spec-correct. Only a unit\n" +
      "\t * still carrying stale EEPROM values runs the block. A factory reset\n" +
      "\t * likewise lands on the correct values without running it, so all three\n" +
      "\t * paths (new unit / existing unit / after factory reset) converge on the\n" +
      "\t * same result.\n",
    new:
      "\t * Marker semantics: Parameter_def[456] is 0, i.e. \"not migrated yet\",\n" +
      "\t * so every unit runs this block once, including a factory-fresh one and\n" +
      "\t * one that has just been factory-reset. Running it on such a unit is\n" +
      "\t * harmless -- the values written are exactly the defaults it already\n" +
      "\t * holds. It must NOT default to the \"done\" value: an EEPROM slot that\n" +
      "\t * has never been written falls back to the default, so a default equal\n" +
      "\t * to the done value would make a never-migrated unit look migrated and\n" +
      "\t * silently skip the fix. (That is exactly the defect this comment now\n" +
      "\t * guards against; it was caught on hardware.)\n",
    count: 1,
  },
];
