// 撤销 2026-09-14 早些时候对 Parameter_def 数组 [345]/[346] 的错误改动。
//
// 那两个索引在运行时被 ParameterInit() 覆盖（Parameter_def[345]=5、[346]=200），
// 所以改数组字面量既无效、值也算错了。正确做法已改到 IndoorMigrateSpecConfiguration()
// 的一次性迁移里（见 tools/byte_patch_spec_param_align.mjs）。这里把数组行还原。
export default [
  {
    file: "PSC330RK-V10-内机/User/UserSrc/user.c",
    old: "   150,   80,   60,   30,   80,    0,  100,    0,    0,    0,",
    new: "   150,   80,   60,   30,   80,    0,    0,    0,    0,    0,",
    count: 1,
  },
];
