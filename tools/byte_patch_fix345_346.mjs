// 修复 2026-09-14 那次越界改动：
//   参数 345 (AirPressureSet 风压设定) 被误写成 100，其 max=1 → 越界，改回 0
//   参数 346 (MinValveOpenSet 冬季阀门最小开度) 仍是 0 → 规格书 3.11.10 不生效，改成 100 (=10.0%)
export default [
  {
    file: "PSC330RK-V10-内机/User/UserSrc/user.c",
    old: "   150,   80,   60,   30,   80,  100,    0,    0,    0,    0,",
    new: "   150,   80,   60,   30,   80,    0,  100,    0,    0,    0,",
    count: 1,
  },
];
