在 `/root/agent_learning/my_agent` 上继续 TUI 方案 A 的实现。只读参考仓库
  `/root/agent_learning/agentty`（含其 TUI 框架 maya 作为
  submodule），**绝不修改**。

  ## 起点

  - 分支 `accelerate/m5-m7`，HEAD `765c006`，180/180 测试绿，工作树干净
  - **`main` 分支全程不动**（那是我按 TDD 手写的学习线）
  - GitHub 远端 `TCWW0/Agent`（gh 已登录）。PRD 是 **#11**，切片是 **#12~#23**
  - 先读 `gh issue view 11 --repo TCWW0/Agent`，再读要做的那个切片
  - 决策记录在 `docs/ACCELERATION_NOTES.md`（原则 1~25）与
  `docs/TUI_NOTES.md`（26~44）

  ## 本轮要做什么

  按 #12 → #13 → #14 → #15 → #16 →（#17~#22 可并行）→ #23 的顺序推进。
  从 **#12** 开始，除非我另外指定。

  ## 硬不变量

  - `HeadlessRunner` 及其测试一行不改
  - `AsyncHost` / `WorkPool` / `WakeSignal` / 领域层 `update()` 一行不改 ——
  事件循环是本项目的核心叙事，Maya 只做渲染
  - **明确拒绝 Maya 的 `run<Program>()`**：它的 `Program` concept 要求
  `update(Model,Msg) → pair<Model,Cmd<Msg>>`，会接管本项目核心。这条拒绝要写进代码注
  释防止日后被当作「简化」重新引入
  - 行式回退路径（非 tty / 管道 / CI）保留
  - 每个实现说明对应 agentty/maya 哪一层
  - 检查点 = 编译通过 + `ctest` 全绿 + 英文描述性 commit + push + 简短中文总结
  - 构建用 `cmake --build build --parallel 2`
  - 中文对我说话，代码/注释/commit/issue 用英文

  ## 已核实的事实（不必重新验证）

  **幽灵行 bug 三处成因**
  1. DECAWM 从未关闭（全仓库 grep `?7l` 零命中），而 `wrap()` 允许「正好填满 columns
   列」的行（判定用 `>` 而非 `>=`，当时刻意）→ 光标越过右边距 → 备用屏滚动 →
  绝对定位 CUP 落到错位行
  2. `terminal.cpp` 的 `frame_bytes` 每行无条件发 `\x1b[K`。**关掉 DECAWM
  后这会变成新 bug**：DECAWM-off 时光标停在第 W-1 列不前进（ECMA-48
  §8.3.118），从那里发 EL 会擦掉刚画的格子。成因 1、2 必须同片修
  3. 宽度表只有 25 条 range 且**完全没有 emoji**。✅U+2705 / ❌U+274C / 🟢U+1F7E2
  全按 1 列算，CJK 扩展 B–F（U+20000..U+2EBE0）整体缺失。Unicode
  官方数据比对：69,107 个已分配非组合码点、59 个区块被漏算

  **顺序理由**：宽度表(#13) 必须排在 DECAWM(#14) 之前 —— 关掉 DECAWM
  后幽灵行**症状会消失但宽度欠算没修好**，会掩盖问题。所以 #13
  带一条负向断言：补完表后 pty 探针仍须失败，证明两成因独立。#13 补的表会在 #17
  被删掉换成 Maya 的，这是「先修再迁」的已知代价，所以 #13 做轻，**不建 Unicode
  生成器流水线**。

  **Maya 分层（已逐条验证）**
  - `element/` 对 `app/` 零引用；`render/` 只有 `canvas.cpp` 摸了一次
  `app/environment.hpp`（读 COLORTERM 判色深）；`widget/` 全层 grep `Ctx`/`Runtime&`
   零命中，turn/tool_call/status_bar 都是 `static Element build(Config)`
  - 唯一接入点：`FrameBuffer::render(const Element&, const Theme&) → const
  std::string&`。**`render()` 不 swap**，调用方须在 write 成功后才 `commit()`；write
   失败跳过 commit，下一帧自动产出完整 diff 而非空 diff
  - `Frame` 自带 `cursor` + `cursor_visible` →
  **原计划的「自己实现光标」切片已取消**
  - `serialize.cpp` 覆盖了我那三处成因：发 `?7l`（两处）、DECAWM-off 跨帧持久只在
  shutdown 还原、行填满至 W-1 列时**跳过 EL**（注释写明正是 DECAWM-off 语义）
  - 宽度表 122 条 wide range + 独立 emoji presentation 表，由 Unicode 官方 txt
  经脚本生成，**生成结果签入仓库故正常构建不需要 Python**；emoji 表运行时由 DECRQM
  mode 2027 探测门控
  - `style/theme.hpp` 有 `dark`/`light`/`dark_ansi`/`light_ansi` 四个 `inline
  constexpr Theme`（约 25 个语义槽位）→ **不用自建调色板**
  - `element/builder.hpp` 的 `fit_row` 接受 `FitItem{el, keep}`，按 keep
  从低到高丢弃直到能放下，always 项永不丢 → **状态栏固定降级阶梯不必自研**
  - Yoga 是自带源码（`src/layout/yoga.cpp`），无传递依赖
  - 单一 `add_library(maya ...)`，41 源文件，**无组件开关** →
  整个目标链上，不能只取渲染层
  - `target_compile_features(maya PUBLIC cxx_std_26)` 会传播（gcc 15.2
  已验证支持，已接受）
  - `MAYA_BUILD_EXAMPLES` 与 `MAYA_NATIVE_TUNING` 默认
  ON，**引入时必须关掉**（后者会把 `-march=native` 烤进二进制）
  - 许可 MIT（上游），已接受。规模对比：maya 115,981 行 vs 本项目 12,161 行

  ## 已定的两个决策

  1. **两段投影**：`Model → 自有 Frame/StyledLine（补样式字段）→
  maya::Element`。理由是现有 11 个 view 测试断言文本子串，跑得最快且可读；直接返回
  `Element` 会让测试变成遍历树并依赖 Maya
  类型。代价（多一薄层、样式语义重定义一遍）已接受
  2. **要写测试的四个模块**：流式 markdown
  边界扫描器、输入编辑器+折行布局、状态栏段模型与降级顺序、transcript 投影（含
  tool_call 卡片四态）

  ## 工作方式

  用 TDD skill：red → green 垂直切片，一个 seam
  一个测试一次最小实现，不做横向切片（不批量先写测试）。每条不变量做**破坏验证**。

  破坏验证的重点：**价值主要在没咬到的那次**。「破坏了还能过」意味着测试没鉴别力**或
  另有一条你不知道的路径** —— 后者是找 bug 的线索，别急着改测试。上一轮三次破坏验证
  全部推翻或修正了我的原判断，其中一次直接暴露了电平 fd 未 drain 的真 bug。

  **单元测试全绿不等于功能可用**，这在本项目已有多次证据（上一轮 pty
  验证抓到两个单测永远发现不了的缺陷：循环用了错的 fd、view 从不渲染
  error）。所以每个切片都要问一次「这条路径真的跑过吗」。验证脚本本身也要验：断言用
  不可能预先存在的哨兵串，基线在副作用发生**之前**抓。

  ## 环境

  - Ollama `localhost:11434`，模型 `qwen3.5:latest`。集成测试在 11434 不可达时
  `GTEST_SKIP()`
  - 想看权限审批要 `MY_AGENT_PROFILE=ask`（默认 `write` 会全部放行）
  - git 操作用 `git -C /root/agent_learning/my_agent` 锁路径；SSH 走 443 端口

  ## 审计线

  #12/#13/#17 都要把对照数字写进 issue 评论（漏算码点范围、range
  条数、构建时间、产物体积、自有代码行数变化），#23 汇总进
  `TUI_NOTES.md`。那份对照就是「为什么先自己写又换成库」的答案，是交付物的一部分。

  开始前先跑一次 `ctest` 确认基线，然后告诉我你打算怎么切第一个红。