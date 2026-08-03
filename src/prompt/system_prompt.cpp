#include "my_agent/prompt/system_prompt.hpp"

#include <filesystem>
#include <string>
#include <system_error>

#if defined(__linux__)
#include <sys/utsname.h>
#endif

namespace my_agent::prompt {
namespace {

constexpr const char* kIdentity =
    "You are my_agent, a command-line coding assistant.\n"
    "\n"
    "You help with software engineering tasks: reading code, running "
    "calculations, and answering questions about the project you are in.\n"
    "\n"
    "Guidelines:\n"
    "- Use the provided tools when they can answer a question more reliably "
    "than guessing. Prefer reading a file over speculating about it.\n"
    "- Keep answers short and concrete. Skip preamble.\n"
    "- If a tool call is rejected, respect the decision and continue without "
    "retrying the same call.\n";

std::string detect_os()
{
#if defined(__linux__)
    utsname info{};
    if (uname(&info) == 0) {
        return std::string{info.sysname} + " " + info.release;
    }
    return "Linux";
#elif defined(_WIN32)
    return "Windows";
#elif defined(__APPLE__)
    return "macOS";
#else
    return "unknown";
#endif
}

}  // namespace

std::string build(const Context& context)
{
    std::string prompt{kIdentity};

    prompt += "\n<environment>\n";
    prompt += "working_directory: " + context.working_directory + "\n";
    prompt += "operating_system: " + context.operating_system + "\n";
    prompt += "</environment>\n";

    // 空块不输出：给模型一个空的 <memory></memory> 是噪声，还可能被当成"确实
    // 没有任何记忆"的强信号。
    if (!context.memories.empty()) {
        prompt += "\n<memory>\n";
        for (const std::string& memory : context.memories) {
            prompt += "- " + memory + "\n";
        }
        prompt += "</memory>\n";
    }

    // 目录整块由 SkillEngine 生成（Tier1 渐进披露：只有名字和一句描述，正文等
    // 模型 activate 才加载），这里只负责放进去。
    if (!context.skills_catalog.empty()) {
        prompt += "\n" + context.skills_catalog + "\n";
    }

    return prompt;
}

Context capture_environment()
{
    std::error_code error;
    std::filesystem::path cwd = std::filesystem::current_path(error);

    return Context{
        .working_directory = error ? std::string{"unknown"} : cwd.string(),
        .operating_system = detect_os(),
    };
}

}  // namespace my_agent::prompt
