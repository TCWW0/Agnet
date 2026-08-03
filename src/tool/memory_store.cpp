#include "my_agent/tool/memory_store.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <random>
#include <sstream>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>

namespace my_agent::tool::memory {
namespace {

namespace fs = std::filesystem;

std::string make_id()
{
    static std::mt19937_64 rng{std::random_device{}()};
    static std::mutex rng_mutex;

    std::uint32_t value = 0;
    {
        const std::lock_guard<std::mutex> lock{rng_mutex};
        value = static_cast<std::uint32_t>(rng());
    }

    char buffer[9];
    std::snprintf(buffer, sizeof(buffer), "%08x", value);
    return std::string{buffer, 8};
}

std::int64_t now_unix()
{
    return std::chrono::duration_cast<std::chrono::seconds>(
               std::chrono::system_clock::now().time_since_epoch()
    ).count();
}

std::string trim(std::string_view text)
{
    std::size_t begin = 0;
    std::size_t end = text.size();
    while (begin < end
           && std::isspace(static_cast<unsigned char>(text[begin])) != 0) {
        ++begin;
    }
    while (end > begin
           && std::isspace(static_cast<unsigned char>(text[end - 1])) != 0) {
        --end;
    }
    return std::string{text.substr(begin, end - begin)};
}

std::string serialise(const Record& record)
{
    // dump() 不带缩进，一条记录天然就是一行。
    return nlohmann::json{
        {"id", record.id},
        {"ts", record.ts},
        {"scope", to_string(record.scope)},
        {"text", record.text},
    }.dump();
}

std::optional<Record> parse_line(std::string_view line)
{
    const std::string text = trim(line);
    if (text.empty()) {
        return std::nullopt;
    }

    const nlohmann::json frame = nlohmann::json::parse(text, nullptr, false);
    if (frame.is_discarded() || !frame.is_object()) {
        return std::nullopt;
    }

    const std::optional<Scope> scope =
        parse_scope(frame.value("scope", std::string{}));
    if (!scope) {
        return std::nullopt;
    }

    Record record{
        .id = frame.value("id", std::string{}),
        .ts = frame.value("ts", std::int64_t{0}),
        .scope = *scope,
        .text = frame.value("text", std::string{}),
    };

    // id 或 text 缺失的记录没有意义：前者无法 forget，后者没有内容可注入。
    if (record.id.empty() || record.text.empty()) {
        return std::nullopt;
    }

    return record;
}

std::vector<Record> read_records(const fs::path& path)
{
    std::vector<Record> records;

    std::error_code error;
    if (!fs::is_regular_file(path, error) || error) {
        return records;
    }

    std::ifstream input{path, std::ios::binary};
    if (!input) {
        return records;
    }

    std::string line;
    while (std::getline(input, line)) {
        // 坏行跳过续读：一条被手工编辑坏掉的记录不该让整个存储不可用。
        if (std::optional<Record> record = parse_line(line)) {
            records.push_back(std::move(*record));
        }
    }
    return records;
}

// 重写存活的行。forget 靠它实现 —— JSONL 按行可寻址，所以「移除」就是
// 「重写没被命中的行」。
std::string write_records(const fs::path& path, const std::vector<Record>& records)
{
    std::error_code error;
    fs::create_directories(path.parent_path(), error);

    std::ostringstream out;
    for (const Record& record : records) {
        out << serialise(record) << '\n';
    }

    std::ofstream output{path, std::ios::binary | std::ios::trunc};
    if (!output) {
        return "failed to open memory file for writing: " + path.string();
    }

    const std::string body = out.str();
    output.write(body.data(), static_cast<std::streamsize>(body.size()));
    if (!output.good()) {
        return "failed to write memory file: " + path.string();
    }
    return {};
}

std::string append_line(const fs::path& path, std::string_view line)
{
    std::error_code error;
    fs::create_directories(path.parent_path(), error);

    std::ofstream output{path, std::ios::binary | std::ios::app};
    if (!output) {
        return "failed to open memory file for appending: " + path.string();
    }

    output.write(line.data(), static_cast<std::streamsize>(line.size()));
    output.put('\n');
    if (!output.good()) {
        return "failed to append to memory file: " + path.string();
    }
    return {};
}

}  // namespace

std::optional<Scope> parse_scope(std::string_view name) noexcept
{
    if (name == "user") {
        return Scope::User;
    }
    if (name == "project") {
        return Scope::Project;
    }
    return std::nullopt;
}

MemoryStore::MemoryStore(Roots roots)
    : roots_{std::move(roots)}
{
}

fs::path MemoryStore::path_for(Scope scope) const
{
    const fs::path& root = scope == Scope::User ? roots_.user : roots_.project;
    if (root.empty()) {
        return {};
    }
    return root / ".my_agent" / "memory.jsonl";
}

AppendResult MemoryStore::append(Scope scope, std::string_view text)
{
    AppendResult result;

    const std::string body = trim(text);
    if (body.empty()) {
        result.error = "remember: text is empty after trim";
        return result;
    }

    const fs::path path = path_for(scope);
    if (path.empty()) {
        // 关键语义：project 不可用时**不**静默回退到 user。一条 project 事实被
        // 提升到 user scope，会加载进**每一个**其他工作区的系统提示 —— 跨工作区
        // 记忆串味。宁可报错，并告诉调用方怎么显式声明全局事实。
        if (scope == Scope::Project) {
            result.error =
                "remember: project scope is unavailable here (no writable "
                "workspace root), so there is nowhere to store a project-scoped "
                "fact. Pass scope=\"user\" if you meant a global fact that "
                "loads into every workspace.";
        } else {
            result.error =
                "remember: cannot resolve a user memory path (HOME is unset)";
        }
        return result;
    }

    Record record{
        .id = make_id(),
        .ts = now_unix(),
        .scope = scope,
        .text = body,
    };

    const std::lock_guard<std::mutex> lock{mutex_};
    const std::string error = append_line(path, serialise(record));
    if (!error.empty()) {
        result.error = "remember: " + error;
        return result;
    }

    result.id = std::move(record.id);
    return result;
}

std::vector<Record> MemoryStore::load_all(Scope scope) const
{
    const fs::path path = path_for(scope);
    if (path.empty()) {
        return {};
    }

    const std::lock_guard<std::mutex> lock{mutex_};
    return read_records(path);
}

std::size_t MemoryStore::forget_by_id(std::string_view id)
{
    const std::string want = trim(id);
    if (want.empty()) {
        return 0;
    }

    const std::lock_guard<std::mutex> lock{mutex_};

    std::size_t removed = 0;
    for (const Scope scope : {Scope::User, Scope::Project}) {
        const fs::path path = path_for(scope);
        if (path.empty()) {
            continue;
        }

        std::vector<Record> records = read_records(path);
        const std::size_t before = records.size();
        std::erase_if(records, [&want](const Record& record) {
            return record.id == want;
        });

        if (records.size() != before) {
            (void)write_records(path, records);
            removed += before - records.size();
        }
    }
    return removed;
}

std::size_t MemoryStore::forget_by_substring(std::string_view needle)
{
    const std::string want = trim(needle);
    // 空 pattern 会匹配所有记录。拒绝，免得一次误调用清空整个存储。
    if (want.empty()) {
        return 0;
    }

    const std::lock_guard<std::mutex> lock{mutex_};

    std::size_t removed = 0;
    for (const Scope scope : {Scope::User, Scope::Project}) {
        const fs::path path = path_for(scope);
        if (path.empty()) {
            continue;
        }

        std::vector<Record> records = read_records(path);
        const std::size_t before = records.size();
        std::erase_if(records, [&want](const Record& record) {
            return record.text.find(want) != std::string::npos;
        });

        if (records.size() != before) {
            (void)write_records(path, records);
            removed += before - records.size();
        }
    }
    return removed;
}

std::string render_for_prompt(const Record& record)
{
    return "[" + record.id + "] " + record.text;
}

Roots discover_roots()
{
    Roots roots;

    if (const char* home = std::getenv("HOME"); home != nullptr && *home != '\0') {
        roots.user = fs::path{home};
    }

    std::error_code error;
    fs::path cwd = fs::current_path(error);
    if (!error) {
        // 根目录不是合理的工作区：任何非 root 用户都写不进 /.my_agent。
        // 留空路径，让 append 报出可操作的错误。
        if (cwd != cwd.root_path()) {
            roots.project = std::move(cwd);
        }
    }

    return roots;
}

}  // namespace my_agent::tool::memory
