# 切片 #15 执行规划 —— 引入 Maya 依赖 + 最小渲染冒烟

写于 2026-08-04。上游 issue：`TCWW0/Agent#15`（父 #11）。分支 `accelerate/m5-m7`。
本文是 #15 动手前的定稿规划，供新会话直接照做。硬不变量见 `docs/HANDOFF_TUI_MAYA.md`，
本文不重复，只记 #15 专属的决策与切法。

## 一句话目标

把 Maya 作为依赖引入构建，用一个最小渲染冒烟证明接入点可用（构造 Element → FrameBuffer
渲染 → 拿到字节）。**不改任何现有渲染路径**，只证明「库能编、能链、能出字节」。

## 已锁定的决策（用户 2026-08-04 拍板，勿倒回）

| 项 | 决定 | 出处 |
|---|---|---|
| 引入方式 | FetchContent 从 git 上游拉取，**不用**本地 `../agentty/maya` 路径 | 用户偏好 |
| 上游 | `https://github.com/1ay1/maya.git` | agentty 同源 |
| 版本 pin | `GIT_TAG cc35bcf5faf8dfddb284b0ac5a531025873765da`（跟 agentty 子模块一致，2026-07-21） | 用户「跟 agentty 用的版本即可」 |
| Maya 可编译 | 已确认，**不单独做去风险构建**；集成验证在红→绿里自然发生 | 用户确认 |
| C++26 | **整个 my_agent 工具链可从 C++23 升到 26**，现有 23 非固化 | 用户授权 |
| 四个 option | `MAYA_BUILD_EXAMPLES=OFF`、`MAYA_NATIVE_TUNING=OFF`；tests/fuzzers 本就 OFF | #15 验收 + maya CMake |
| `run<Program>()` 拒绝注释 | 落到引入 maya 的 CMake 注释即可 | 用户「不重要」 |
| wrapper 层 / 审计基线细节 | 助手自由裁量 | 用户授权 |

**C++26 松绑的含义**：原本考虑「用 wrapper 库隔离 maya 的 C++26 PUBLIC 传播」——该理由已消失。
是否仍要一层薄适配，只看「两段投影」渲染架构本身需不需要（渲染设计问题，非构建隔离问题）。

## 接入点 seam（唯一，已核实）

```
maya::render::FrameBuffer fb(width, height);          // 双缓冲
maya::Element ui = maya::text("...");                 // 最小 Element（namespace maya）
const std::string& bytes = fb.render(ui, maya::theme::dark);  // 不 swap，返回引用
fb.commit();                                          // swap；write 成功后才调
```

- 头：`maya/render/frame.hpp`、`maya/element/builder.hpp`、`maya/style/theme.hpp`（或伞头 `maya/maya.hpp`）。
- `render()` **不 swap**：调用方 write 成功后才 `commit()`；write 失败跳过 commit，
  front 不前进，**下一帧自动产出完整 diff 而非空 diff**（这是 #15 验收第 4 条要断言的核心语义）。
- Theme：`maya::theme::{dark,light,dark_ansi,light_ansi}` 四个 `inline constexpr`，选其一，不自建调色板。

## 垂直切片（红 → 绿，一缝一测一实现）

**第 0 步（非测试，但必须最先做）——采审计基线。**
动任何 CMake 之前，用一次 clean 全量构建采「前」值：`my_agent_repl` 体积 + 全量构建墙钟。
错过这个时点就没有真正的对照起点。记下数字，留给最后写 issue 评论。

**切片 A —— 库能链、能出非空字节。**
- 红：新建 `tests/maya_smoke_test.cpp`，构造 `maya::text("<哨兵串>")` → `FrameBuffer::render(ui, maya::theme::dark)`
  → 断言返回字节**非空**且**含哨兵串**（哨兵证明真渲染了我的内容，不是任何预存字节）。
  此刻 `maya` target 不存在 → 编译/链接红。
- 绿：CMakeLists 加 `FetchContent_Declare(maya GIT_REPOSITORY ... GIT_TAG cc35bcf...)`，
  引入前预置两个 option 的 `CACHE INTERNAL`，`FetchContent_MakeAvailable(maya)`，
  新增 `maya_smoke_test` target 链 `maya`（加别名/`SYSTEM` 抑制头警告），
  按需把工具链升 C++26。转绿。

**切片 B —— commit 语义。**
- 红：断言「render 后 commit，再 render 同内容 → diff 为空」且「render 后**跳过** commit，
  下一帧 render → 完整 diff（非空）」。（若切片 A 的实现已顺带满足，B 退化为纯加断言的一步。）
- 绿：无需改生产码——这是 maya 自带语义，测试是在**钉住我们依赖的那条契约**，防止日后版本漂移破坏它。

**切片 C —— C++26 升级的破坏验证 + 回归门。**
- 升 C++26 后跑全量 ctest，确认现有 195 条不回归（升级的破坏验证点：编译器标准变了，
  模板/`constexpr`/库特性有无行为差异）。
- 真 pty 实测 `./build/my_agent_repl`：进备用屏、渲染输入行、干净还原——证明既有 REPL
  与行式回退**行为不变**（#15 验收第 7 条，单测全绿≠功能可用）。

## 验收标准逐条 → 切片映射

| #15 验收 | 落在 |
|---|---|
| Maya 以既有依赖惯用法引入并成功构建 | 切片 A |
| `MAYA_BUILD_EXAMPLES` 与 `MAYA_NATIVE_TUNING` 均关闭 | 切片 A（预置 CACHE INTERNAL） |
| 冒烟：最小 Element → 渲染 → 断言非空字节 | 切片 A |
| 冒烟：write 成功后 commit、跳过时下一帧完整 diff 非空 | 切片 B |
| 确认自带 Theme 可用，选定其一作默认 | 切片 A（`maya::theme::dark`，除非 B 另择） |
| 记录引入前后构建时间与产物体积，写入 issue 评论 | 第 0 步采「前」+ 切片 C 后采「后」→ 评论 |
| 既有 REPL 与行式回退行为不变 | 切片 C（真 pty 实测） |
| 既有测试全绿 | 切片 C（195 不回归） |

## #15 专属注意 / 破坏验证点

- **升 C++26 是全局一把升还是只升相关 target**：倾向全局（用户已授权工具链升级），
  但全局升的破坏验证 = 现有 195 条不回归。若某目标出问题，退回「只升链 maya 的 target」。
- **maya 的 `CMAKE_BUILD_TYPE` FORCE**：maya CMake 仅在 `NOT CMAKE_BUILD_TYPE` 时 FORCE Release。
  my_agent 已设 Debug，FORCE 不触发——但引入后要**核实缓存里 build type 没被顶掉**（破坏验证：
  configure 后 grep `CMAKE_BUILD_TYPE`，仍是原值才算没被 maya 顶掉）。
- **maya 嵌套子模块漂移**：`agentty/maya` 里 `agentic-loop`/`glyph` 等有预存漂移，与本项目无关；
  走 FetchContent 从上游拉取会得到干净的 pin，不受本地漂移影响——这也是不用本地路径的又一好处。
- 冒烟测试哨兵串用不可能预存的记号，基线在渲染**之前**采（沿用本项目验证纪律）。

## 对后续工作的对接（务必留给 #16+）

- **#16「两段投影骨架」是 #15 seam 的第一个消费者**：`StyledLine` 加样式字段 → 投影成
  `maya::Element` → 交 `FrameBuffer`。#15 只证明 seam 通；#16 才把 `Model → 自有 Frame/StyledLine
  → maya::Element` 的两段投影骨架搭起来（HITL，需人审）。所以 #15 的冒烟测试要写成**可被 #16 扩展的样子**：
  把「构造 Element → render → 断言字节」的调用范式立清楚，#16 直接沿用。
- **#17 会删掉 #13 补的自有宽度表、换成 maya 的**（「先修再迁」的已知代价，#13 已注明做轻）。
  #15 引入 maya 后，maya 自带 122 段 wide range + emoji presentation 表就位，#17 的迁移前提即成立。
- **审计线**：#15 的构建时间/体积对照写进 #15 评论；#23 汇总进 `TUI_NOTES.md`。
  这份对照是「为什么先自己写宽度表又换成库」叙事的一部分（配合 #12/#13 已有的数字）。
- **拒绝 `run<Program>()`**：注释落 CMake；实现层面全程只用 `FrameBuffer::render`，绝不引入
  `update(Model,Msg)→pair<Model,Cmd>` 那套——它会接管本项目核心事件循环。

## 检查点

编译通过 + `ctest` 全绿 + 英文描述式 commit + push + 中文简短汇报。临时文件放本会话临时目录，不放 `/tmp`。
