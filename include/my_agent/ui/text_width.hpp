#pragma once

#include <string>
#include <string_view>
#include <vector>

namespace my_agent::ui {

// 单个码点的终端显示宽度，单位是列。
//   0 — C0 控制字符
//   1 — 窄字符（ASCII、拉丁、框线、希腊西里尔……）
//   2 — East_Asian_Width 为 Wide/Fullwidth 的字符，以及有 emoji 表现形式的字符
[[nodiscard]]
int char_width(char32_t code_point) noexcept;

// 文本的**终端显示宽度**，单位是列。
//
// 字节数 ≠ 码点数 ≠ 显示宽度：ASCII 三者相等，但一个汉字是 3 字节 / 1 码点 /
// 2 列。折行必须按列算，否则中文会把边框顶歪。
//
// 非法 UTF-8 字节按 1 列计并跳过一个字节 —— 度量函数不是校验器，遇到脏数据要
// 继续给出一个可用的数，而不是抛异常或返回 0 让调用方去猜。
[[nodiscard]]
int display_width(std::string_view text);

// 按显示宽度把文本折成不超过 columns 列的若干行。
//
// 绝不切开一个字符：宽字符卡在边界上时整个推到下一行，宁可留一列空白 ——
// 切开会产生非法 UTF-8，终端显示成乱码方块。这是折行里唯一会损坏数据的错误。
[[nodiscard]]
std::vector<std::string> wrap(std::string_view text, int columns);

}  // namespace my_agent::ui
