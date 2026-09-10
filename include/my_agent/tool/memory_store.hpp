#pragma once

#include <cstdint>
#include <filesystem>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace my_agent::tool::memory {

// remember / forget 两个工具背后的存储层，也是系统提示每轮读取的来源。
//
// 落盘格式是 JSONL，每条记录一行：
//
//   {"id":"a1b2c3d4","ts":1731860000,"scope":"project","text":"prefer fish"}
//
// 选 JSONL 而不是单个 JSON 文档，有三个理由：
//   1. 追加一条就是一次 append 写 `<record>\n`，不需要读-改-写整个文件。
//   2. 文件按行可寻址：forget 剔掉命中的行、重写存活的行。坏行只影响那一条，加载时跳过续读。
//   3. grep 友好 —— 人要审计 agent 存了什么关于自己的事实时，直接看得懂。
enum class Scope : std::uint8_t {
    User,     // 跨工作区共享
    Project,  // 按项目隔离，进 .gitignore
};

[[nodiscard]]
constexpr std::string_view to_string(Scope scope) noexcept
{
    return scope == Scope::User ? "user" : "project";
}

[[nodiscard]]
std::optional<Scope> parse_scope(std::string_view name) noexcept;

struct Record {
    std::string id;    // 8 位十六进制，append 时分配
    std::int64_t ts{}; // unix 秒
    Scope scope{Scope::User};
    std::string text;
};

struct AppendResult {
    std::string id;     // 成功时是新记录的 id
    std::string error;  // 成功时为空
};

// 两个 scope 的根目录。空路径表示该 scope 在当前环境下不可用 —— 比如没有 HOME，
// 或工作区根不可写。构造时注入而不是内部去读环境，这样纯逻辑可以喂临时目录测。
struct Roots {
    std::filesystem::path user;
    std::filesystem::path project;
};

class MemoryStore {
public:
    explicit MemoryStore(Roots roots);

    // 纯函数，不碰文件系统。scope 不可用时返回空路径。
    [[nodiscard]]
    std::filesystem::path path_for(Scope scope) const;

    [[nodiscard]]
    AppendResult append(Scope scope, std::string_view text);

    // 按写入顺序返回（最旧在前）。文件不存在返回空，坏行跳过续读。
    [[nodiscard]]
    std::vector<Record> load_all(Scope scope) const;

    // 两个 scope 都找。返回移除条数。
    [[nodiscard]]
    std::size_t forget_by_id(std::string_view id);

    // 子串匹配（大小写敏感），两个 scope 都找。空 needle 直接拒绝，
    // 免得一次误调用清空整个存储。
    [[nodiscard]]
    std::size_t forget_by_substring(std::string_view needle);

private:
    Roots roots_;
    // 工具在隔离线程上执行，remember 与 forget 可能背靠背发生。
    // 读-改-写整体串行化，代价可以忽略。
    mutable std::mutex mutex_;
};

// 唯一碰环境的函数：user 取 $HOME，project 取 cwd。任一不可用时留空路径，
// 由 append 报出可操作的错误，而不是静默换个地方写。
[[nodiscard]]
Roots discover_roots();

// 渲染成系统提示 <memory> 块里的一行：`[<id>] <text>`。
// id 必须出现 —— 模型只有看得到 id，才能在用户说「忘掉那条」时精确调 forget。
[[nodiscard]]
std::string render_for_prompt(const Record& record);

}  // namespace my_agent::tool::memory
