# 答辩速查卡 — 两轮平衡赛车数字孪生

> 仓库：`github.com/rim5432/mujoco-renode-twin` @ `5582e17`（MIT）
> 本机工作区：`~/jupyter_workspace/学习/mujoco-renode-twin/`（已 git 化，5 次提交）
> 核实日期：2026-10-09　　实测环境：macOS arm64 / Python 3.14 / MuJoCo

---

## 一句话讲清这个项目

**在电脑里造一辆和实物完全一样的两轮平衡赛车**：物理引擎算真实的重力摩擦，控制器跑的是**能烧进板子的那份真实固件**，参数在电脑上改完秒级验证，不用每次烧录跑赛道。

评委如果只问一句「这和直接烧板子有什么区别」，答：

> 实物调参一轮要几分钟且失败不可复现；这里一轮是秒级、且能回放。**更重要的是电脑上调好的参数，能证明就是烧到车上会跑的那个行为**——因为跑的是同一份固件二进制。

---

## 现在能当场演示的（已实测通过）

### 1. 四任务判决表 —— 最硬的一张表

```bash
uv run python -m race --all
```

实测输出（hostc 后端）：

| task | pass | 耗时 | 限时 | 停车误差 | 蜂鸣 |
|---|---|---|---|---|---|
| 1 | ✅ | 4.68 s | 15 s | 0.02 m | ✅ |
| 2 | ✅ | 18.89 s | 30 s | 0.05 m | ✅ |
| 3 | ✅ | 24.57 s | 40 s | 0.02 m | ✅ |
| 4 | ✅ | 96.64 s | — | 0.03 m | ✅ |

**四个任务全过，含摔倒检测（`fallen: false`）与蜂鸣序列校验。**

### 2. 3D 浏览器演示

```bash
bash tools/demo.sh     # 一条命令拉起全部
```
打开 `http://localhost:5173/?ws=ws://127.0.0.1:8766`

已验证画面（见 `docs/defense-viewer-task1.png`）：车模实时姿态、HUD 实时
`Tilt / Pos / Speed / Duty L/R / Enc L/R / Batt`、**8 通道红外循迹阵列**实时
读数（哪几个探头压黑线一目了然）、4 个任务一键切换、4 档回放倍速。

> ⚠️ **必须在 Chrome/Safari 打开**。Codex 内置的沙箱浏览器连不上
> 127.0.0.1:8766，会一直显示 offline——那是沙箱限制，不是项目问题
> （已用独立 Chromium 验证：零 console error，全链路通）。

### 3. 固件在环（可讲，不一定能现场跑）

```bash
source tools/f407_env.sh
bash firmware/twin/build.sh && bash firmware/race/build.sh   # 已验证：71880 / 151936 字节
uv run python -m race --task 2 --backend renode              # 需 portable Renode
```

本机 `/Applications/Renode.app` 是**桌面版**，pyrenode3 要的是 portable
.NET 包，所以固件在环目前是 skip 状态。**答辩时如实说"代码路径已通，
本机缺 portable Renode"即可**，别硬说跑过了。

---

## 三个技术亮点（按答辩价值排序）

### 亮点 1：三个控制器槽，同一接口，可 A/B 对比

物理侧永远不变，「大脑」可插三种，走**完全相同**的接口
`controller.step(sensor) → motor`：

| 槽 | 是什么 | 用途 |
|---|---|---|
| `stub` | Python 控制算法 | 验证环境通不通 |
| `hostc` | 同一份 C 源码编成宿主库 | **日常调参，最快** |
| `renode` | **真实固件 ELF** 跑在 ARM 模拟器 | 最终验证"烧上去就是这个行为" |

三槽同接口 → 同一场景跑三份，输出逐点一致就**证明了"电脑上调的参数 = 真车行为"**。

### 亮点 2：自研 9 个 C# 外设模型

Renode 里模拟 STM32F407。这个仓库**自己写了 C# 外设模型**
（`firmware/*.cs`：mpu6050、编码器、定时器、ADC、I2C、GPIO、看门狗、UART、RCC）——
真车接什么线，模拟器就灌什么信号。这是让真实固件在 PC 上"以为自己在芯片上"的关键。

### 亮点 3：参数单一数据源 + 防漂移门

```
Python 参数（唯一数据源）
   │ python -m race.fwconfig
生成的 C 头文件 race_fwconfig.h
   │ bash firmware/race/build.sh
真实固件 ELF
```
`--check` 子命令：手改了 .h 或改了 Python 忘同步 → **exit 1**。
保证 C 固件和 Python 仿真**永远同一套参数**——这是孪生成立的基础。

---

## 数据支撑（评委问"工程量"时用）

| 指标 | 数量 |
|---|---|
| Python | 80 文件 / 12,844 行 |
| C 固件 | 48 文件 |
| 自研 C# 外设模型 | 9 个 |
| 测试 | 23 文件 / **227 个测试函数** |
| 测试现状 | **138 passed / 81 skipped / 8 failed** |

> 8 个 failed 是**环境限制不是缺陷**，如实说明：
> 6 个需要 portable Renode，2 个是 macOS 上 `race/diagnostics.py` 只解析 PE 镜像
> （源码里明确写了 `requires a PE DLL`），故 hostc 符号检查必然 `available: False`。

---

## 已知坑（被问到 macOS 兼容性时）

1. **`ops.py` 是 Windows 专用**（netstat/taskkill/powershell）→ Mac 手动起两个终端，或用 `tools/demo.sh`
2. README 写 Python ≥3.12，`pyproject.toml` 实为 **≥3.14**
3. vendor STEP 模型**故意不分发**（第三方许可）→ 首次跑必须 `bash tools/fetch_vendor.sh`
4. Homebrew 的 `arm-none-eabi-gcc` **无 newlib** → `source tools/f407_env.sh`（已封装 Debian newlib）

---

## 可能被问到的挑战问题 → 建议答法

**Q：仿真参数和实物对不上怎么办？**
A：这是数字孪生的核心难点，项目里预留了 30 项「仿真↔实物」映射表的设计
（断电测量 / 上电电气 / 闭环标定三个阶段，每项标注测量方法、代码位置、验证命令）。
**诚实说明**：这张映射表随 10-06 的临时工作区丢失尚未重建，但它体现了方法论——
孪生的可信度不来自"仿真多真实"，而来自"每一项参数都能追溯到实测"。

**Q：为什么不用 Gym/PyTorch 学控制？**
A：目标是控制**已有的 C 固件**，不是训新策略。PID/LQR 参数必须在真实固件代码里生效，
所以瓶颈是"让真固件在 PC 上跑起来"，这正是 Renode + 自研外设模型解决的事。

**Q：仿真里刷分算作弊吗？**
A：评分器（grader）拿的是 MuJoCo 状态真值，而控制器只能看到和真车一样的原始传感器
（加速度 int16、编码器计数），输出只能是电机占空比。**控制器拿不到物理引擎内部状态**。

---

## 答辩前一分钟检查清单

```bash
cd ~/jupyter_workspace/学习/mujoco-renode-twin
bash tools/fetch_vendor.sh          # 幂等，已拉过会 skip
uv run python -m race --all         # 确认四任务仍全绿
bash tools/demo.sh                  # 起 3D 演示
```
然后用 **Chrome** 打开 `http://localhost:5173/?ws=ws://127.0.0.1:8766`，
**不要**用 Codex 内置浏览器。