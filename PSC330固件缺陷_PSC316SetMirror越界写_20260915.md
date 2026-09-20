# PSC330 固件缺陷：写 316 AI 配置时 `PSC316SetMirror` 越界写

- **发现日期**：2026-09-15
- **发现途径**：上位机（Python 监控工具）写 316 AI 配置时报错，追查报错成因时发现
- **引入提交**：`e20972a`（feat(PSC316): AI 通道配置块 + 网关发布，2026-09-14）—— 随 AI 配置窗口一起引入
- **影响**：**每次经网关写 316 AI 配置都会越界写 330 的静态内存**
- **优先级建议**：高（静默内存破坏，症状随机、难定位）

---

## 1. 缺陷位置

`PSC330RK-V10-内机/User/UserSrc/modulecontrol.c`，写任务完成处理函数（约 698~775 行），`else` 分支（约 750~758 行）：

```c
if((value[0] == PSC316WriteJob.value[0])
    &&((PSC316WriteJob.count == 1) || (value[1] == PSC316WriteJob.value[1])))
{
    if((PSC316WriteJob.addr >= PSC316_CAL_SAVED_BASE)          // 486~499
        && (PSC316WriteJob.addr < (PSC316_CAL_SAVED_BASE + PSC316_CAL_SAVED_WORDS)))
    { ... }
    else if((PSC316WriteJob.addr >= 1506) && (PSC316WriteJob.addr <= 1513))
    { ... }
    else if((PSC316WriteJob.addr >= PSC316_EEV_MANUAL_BASE)     // 155~158
        && (PSC316WriteJob.addr < (PSC316_EEV_MANUAL_BASE + PSC316_EEV_MANUAL_WORDS)))
    { ... }
    else
    {
        offset = PSC316WriteJob.addr - PSC316_SET_BASE;         // ★ PSC316_SET_BASE = 165
        for(i=0; i<PSC316WriteJob.count; i++)
        {
            PSC316SetMirror[unitIndex][offset+i] = value[i];    // ★ 越界
        }
        PSC316SetValid[unitIndex] = 1;
    }
    PSC316WriteState[unitIndex] = 2;
    ...
}
```

数组声明（同文件第 30 行）：

```c
static int16_t PSC316SetMirror[PSC316_HMI_UNIT_NUM][PSC316_SET_NUM];   // [4][42] = 168 个 int16
```

## 2. 触发条件

`PSC316Gateway_HMIWrite()` 对 AI 配置地址（2680~2875）算出的目标地址是：

```c
targetAddr = PSC316_AI_CFG_SRC_BASE + offset;    // 302 + offset，范围 302~349
```

**302~349 不落在上面任何一个前置分支里**（前置分支只覆盖 486~499、1506~1513、155~158），因此**必然进入 `else`**，于是：

```
offset = 302+off - 165 = 137 + off        （off = 0~47）
```

即 `PSC316SetMirror[unitIndex][137..184]`，而该行只有 42 个元素。

## 3. 越界程度与命中区

元素下标 = `unitIndex * 42 + offset`，数组共 168 个元素：

| 写哪台 (unitIndex) | 元素下标 | 相对数组末尾 |
|---|---|---|
| 1# (0) | 137 ~ 184 | 行内（但落到**第 4 台那一行**），末尾越界 0~16 个 |
| 2# (1) | 179 ~ 226 | 越界 11 ~ 58 个（22 ~ 116 字节） |
| 3# (2) | 221 ~ 268 | 越界 53 ~ 100 个（106 ~ 200 字节） |
| 4# (3) | 263 ~ 310 | 越界 95 ~ 142 个（190 ~ 284 字节） |

按声明顺序（同文件 31~47 行），越界区覆盖到的静态变量：

| 距数组末尾的字节 | 被覆盖的变量 |
|---|---|
| 0 ~ 3 | `PSC316StatusValid` |
| 4 ~ 7 | `PSC316SetValid` |
| 8 ~ 23 | `PSC316StatusOkCount` / `PSC316SetOkCount` |
| 24 ~ 31 | `PSC316LastReadAddr` |
| **32 ~ 35** | **`PSC316WriteState`** ← 写状态本身 |
| **36 ~ 39** | **`PSC316WriteError`** ← 写错误码本身 |
| 40 ~ 56 | `PSC316RuntimePending` / `PSC316VersionValid` / `…RequestPending` / `…RequestRetry` |
| 57 ~ 64 | `PSC316FaultLatch` |
| 65 ~ 96 | `PSC316PressureCalibrationMirror` |
| 105 ~ 497 | `PSC316AiCfgMirror`（AI 配置镜像本身） |

> 注：字节偏移按声明顺序累加估算，实际以链接器布局为准；**顺序是确定的**。

## 4. 现场可观察到的症状

1. **写 1# 外机 AI 配置会篡改 4# 外机的设置镜像**（`[0][137..167]` 落在第 4 行的存储区），4# 机 HMI 上的设置值显示错乱。
2. **写 2#/3#/4# 外机 AI 配置会越出数组**，破坏相邻静态变量；其中 `PSC316WriteState` / `PSC316WriteError` 被破坏时，上位机看到的是随机的"网关忙"/错误码，或写任务状态永远不归位。
3. 由于 `PSC316AiCfgMirror` 本身也在命中区内，**AI 配置镜像可能被自己写坏**，表现为读数随机跳变。

已实测到的两条上位机报错（均由该缺陷或其后果引起）：

- `316写入及直接回读成功，但330校准镜像未刷新: PSC316[303]=1, 镜像回读=0`
- `330网关忙超时: 状态=1, 错误码=0`

## 5. 复现步骤

1. 330 + 至少一台 316 正常在线
2. 上位机（Python 监控工具）→「AI 通道配置」页 → 任一 316 外机
3. 改任一字段（如 AI0 的"信号类型"）→ 点该格后的「写」

第 1 步的写入就已经触发越界（该缺陷与上位机实现无关，上位机只是触发者）。

## 6. 建议修法

在链式判断里加一个 AI 配置分支，**只更新对应镜像、不落进 `else`**：

```c
else if((PSC316WriteJob.addr >= PSC316_AI_CFG_SRC_BASE)
    && (PSC316WriteJob.addr <
        (PSC316_AI_CFG_SRC_BASE + PSC316_AI_CFG_CHANNELS * PSC316_AI_CFG_WORDS)))
{
    /* 316 AI 配置由 316 的发布块 (PSC316_AI_CFG_PUB_BASE) 轮询回来后
       经 PSC316AiCfgMirror 填充，这里不做镜像更新。 */
}
```

更稳妥的做法（防御性）：把 `else` 分支的下标也加一道边界检查，例如

```c
offset = PSC316WriteJob.addr - PSC316_SET_BASE;
if((offset < 0) || ((offset + PSC316WriteJob.count) > PSC316_SET_NUM))
{
    /* 不在设置窗口内的地址不应走镜像更新 */
}
else
{
    for(i=0; i<PSC316WriteJob.count; i++)
        PSC316SetMirror[unitIndex][offset+i] = value[i];
    PSC316SetValid[unitIndex] = 1;
}
```

这样即使将来再加新的地址区间也不会重蹈覆辙。

## 7. 附：上位机侧的两处误报（已修，与固件缺陷无关）

追查过程中同时修掉了上位机的两处误报，它们**不是**固件问题，但会把上面这个
固件缺陷的症状放大成"看起来像上位机坏了"：

| 误报 | 原因 | 修复 |
|---|---|---|
| `330校准镜像未刷新` | AI 配置窗口的镜像只由 330 周期轮询 316 的发布块(1528) 后填充，刷新时机晚于写完成；上位机只等 2 秒就判失败 | 改以 330 的写状态（`state==2` = 已写入并读回校验）为准，镜像滞后最多再等 3 秒，不再判失败 |
| `330网关忙超时: 状态=1` | 330 的写任务最多重试 3 次、每次重试都把状态置 1，一次合法任务可明显超过 8 秒；上位机只等 8 秒 | 空闲等待时限由 8 秒改为 30 秒，与完成等待的 45 秒同量级 |

上位机提交：`4af4f2c`、`e3921ad`（仓库 `psc330_monitor_tool`）。
