# 交接 — my_agent TUI Plan A，下一片是 #14

写于 2026-08-04。上一份总纲是 `/root/agent_learning/my_agent/docs/HANDOFF_TUI_MAYA.md`，
里面的硬性不变量（`main` 分支全程不动、`agentty`/`maya` 只读、明确拒绝 Maya 的
`run<Program>()`、`HeadlessRunner` 与 `AsyncHost`/`WorkPool`/`WakeSignal`/领域层
`update()` 一行不改、行式回退路径保留）**全部继续有效**，本文不重复。

## 当前状态

- 仓库 `/root/agent_learning/my_agent`，分支 `accelerate/m5-m7`，HEAD `40f9339`，
  已推送，工作树干净。
- `ctest` 194 条：193 绿，**1 条刻意留红** ——
  `ghost_line_probe.GhostLineProbeTest.ALineThatExactlyFillsTheWidthKeepsItsLastCell`。
  它是 #14 的转绿目标，不是回归。
- #13 已完成但 issue **保持 OPEN**。惯例：留红的切片在红转绿前不关（#12 同样 OPEN）。
- 构建命令 `cmake --build build --parallel 2`。远端 `TCWW0/Agent`，PRD 是 issue #11。

## 本轮（#13）做了什么

不在这里重复，去看：

- commit `b62c1e7` — 宽度表 22→122 段、43,694→182,719 码点，以及为什么只取
  EAW `W|F`、为什么合并不算外推、为什么不建生成链、为什么加 `static_assert`。
- commit `40f9339` — 替换掉 #13 那条被实测推翻的负向断言，以及新探针的设计约束。
- issue #13 评论 <https://github.com/TCWW0/Agent/issues/13#issuecomment-5174083429>
  — 对照数字、验收标准逐条、两次破坏验证、给 #14 的提醒。

一句话概括：#13 要求「补完宽度表后 #12 的两条 pty 探针仍须失败」，实测**两条同时
转绿** —— 欠算是把行推到右边距的那个力，宽度修对之后 `tail_within` 按真实宽度裁剪，
输入行够不到边距，DECAWM 无从咬起，两者串联而非独立。替代的真负向断言是「正好填满
一行的最后一格被无条件 EL 吃掉」（纯 ASCII，不过任何宽度判断）。

## 下一片：#14 —— 让那条红转绿

两件事。第一件是主体，第二件是纵深防御。

### 1. 填满至第 W-1 列的行不再发 EL

缺陷在 `src/ui/terminal.cpp:185` 的 `frame_bytes()`：每行画完无条件发 `\x1b[K`。
光标停在第 W-1 列时（pending wrap 已置位、尚未真换行），EL 从光标处擦到行尾 ——
擦掉的正是刚画上去的那一格。

**签名要改。** `frame_bytes(const Frame&)` 现在拿不到宽度
（`include/my_agent/ui/terminal.hpp:14`）。唯一的生产调用方
`TerminalDriver::render`（`src/ui/terminal.cpp:127`）手上有 `size()`，把列数穿进去。
测试里有四处调用（`tests/terminal_test.cpp` 三处、`tests/ghost_line_probe_test.cpp:278`），
改签名会让它们一起编译失败 —— 那是好事，每处都得重新想清楚该传几列。

**别图省事直接删 EL。** `tests/terminal_test.cpp` 的
`ErasesToEndOfEachLineSoLongerPreviousLinesLeaveNoResidue` 守着另一侧，删了立刻变红。
判据是「这一行的显示宽度是否正好等于终端宽度」，宽度要用 `ui::display_width` 算，
不是 `.size()` —— CJK 行的字节数远大于列数。

### 2. `enter_bytes()` 里关掉 DECAWM

`src/ui/terminal.cpp:56` 现在是 `"\x1b[?1049h\x1b[?25l"`，没有 `\x1b[?7l`。
#12 那两条 pty 探针已经因 #13 的宽度修复转绿，所以**这一条没有红测试可写**。
用户已认可按纵深防御处理：直接加 `\x1b[?7l`，注释里写明它防的是「宽度表跟不上
Unicode 新分配时的漏网字符」而不是当前已知缺陷；`leave_bytes()`
（`src/ui/terminal.cpp:63`）要精确逆转，加 `\x1b[?7h` 且顺序相反。
**不要为它造一条假探针。**

## 用户最后问的问题 —— 还没答完

原问：**「哪一次切片过后我才可以直接启动程序、在终端里看到 TUI 效果？」**

我在收集证据时被打断了。已核实的部分（有工具输出为证）：

- `src/repl/main.cpp:227` 先调 `run_ui(host_runtime, terminal)`，只有它返回 false
  （非 tty）才落到 `run_line_repl`。**TUI 已经是默认前端**，不是待建功能 ——
  那是 HEAD 之前的 commit `190a69f`「Make the TUI the default frontend」做的。
- `build/my_agent_repl` 在（20 MB，8月4日 10:54）。
- Ollama 活着，`localhost:11434` 有 `qwen3.5:latest`。

所以答案大概是**「现在就能跑」**，而不是某个未来切片。但我**没有实测过**：没在真
pty 里启动过二进制，那次尝试正好撞上空返回窗口。这个结论目前只建立在读 `main.cpp`
加上两条 pty 探针（它们同步在 `\x1b[?1049h` 上，证明驱动确实进备用屏）之上。

**下一个 agent 该先做的事**：在真终端里跑一次 `./build/my_agent_repl`，据实回答，
不要照抄我的推断。

还有一处我没确认完：`tool_call` 是否**完全**不上屏。我读 `src/ui/view.cpp` 到第 72
行被打断，帧的组装在那之后（`view()` 在第 98 行起）。按 #18 的描述应该是不渲染的，
但请自己核实一遍再对用户下断言。

现在屏幕上有的：历史消息带说话人前缀（`> ` / `* `）、正文折行、状态行
（`... thinking` / `... running <tool>` / `allow <tool>? [y/n]`）、输入行横向滚动。
可见缺陷：正好填满终端宽度的行少最后一格（#14 修）。

