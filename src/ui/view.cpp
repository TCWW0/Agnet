#include "my_agent/ui/view.hpp"
#include "my_agent/ui/input_layout.hpp"
#include "my_agent/tool/tool.hpp"

#include <algorithm>
#include <cstddef>
#include <iterator>
#include <string>
#include <string_view>
#include <type_traits>
#include <variant>
#include <vector>

namespace my_agent::ui {

namespace {

constexpr std::string_view kInputPrompt = "> ";
constexpr std::size_t kMaxToolOutputCharacters = 240;
constexpr std::string_view kTurnRail = "│";

[[nodiscard]]
StyleColor turn_rail_color(Role role) noexcept
{
    return role == Role::User ? StyleColor::Accent : StyleColor::Primary;
}

void apply_turn_rail(StyledLine& line, Role role)
{
    line.rail = std::string{kTurnRail};
    line.rail_foreground = turn_rail_color(role);
}

[[nodiscard]]
const ToolCall* tool_call_for(const Model& model, const std::string& id)
{
    for (auto message = model.thread.messages.rbegin();
         message != model.thread.messages.rend();
         ++message) {
        for (auto call = message->tool_calls.rbegin();
             call != message->tool_calls.rend(); ++call) {
            if (call->id == id) {
                return &*call;
            }
        }
    }
    return nullptr;
}

[[nodiscard]]
std::string tool_name_for(const Model& model, const std::string& id)
{
    if (const ToolCall* call = tool_call_for(model, id)) {
        return call->name;
    }
    return id;
}

[[nodiscard]]
std::string effect_label(tool::EffectSet effects)
{
    std::string result;
    const auto append = [&result](std::string_view label) {
        if (!result.empty()) {
            result += ',';
        }
        result += label;
    };
    if (effects.has(tool::Effect::ReadFs)) {
        append("read_fs");
    }
    if (effects.has(tool::Effect::WriteFs)) {
        append("write_fs");
    }
    if (effects.has(tool::Effect::Net)) {
        append("net");
    }
    if (effects.has(tool::Effect::Exec)) {
        append("exec");
    }
    return result.empty() ? "none" : result;
}

[[nodiscard]]
std::size_t utf8_codepoint_count(std::string_view text) noexcept
{
    std::size_t count = 0;
    for (const unsigned char byte : text) {
        if ((byte & 0xc0u) != 0x80u) {
            ++count;
        }
    }
    return count;
}

[[nodiscard]]
std::string truncate_tool_output(std::string_view output)
{
    if (utf8_codepoint_count(output) <= kMaxToolOutputCharacters) {
        return std::string{output};
    }

    std::size_t visible_end = 0;
    std::size_t visible_characters = 0;
    while (visible_end < output.size()
           && visible_characters < kMaxToolOutputCharacters) {
        const unsigned char byte = static_cast<unsigned char>(output[visible_end]);
        const std::size_t width = (byte & 0x80u) == 0
            ? 1
            : (byte & 0xe0u) == 0xc0
                ? 2
                : (byte & 0xf0u) == 0xe0 ? 3 : 4;
        if (visible_end + width > output.size()) {
            break;
        }
        visible_end += width;
        ++visible_characters;
    }

    const std::size_t elided = utf8_codepoint_count(output.substr(visible_end));
    return std::string{output.substr(0, visible_end)}
        + " [... " + std::to_string(elided) + " characters elided]";
}

struct FenceLine {
    bool is_fence{false};
    bool closes_fence{false};
    std::string language;
};

[[nodiscard]]
FenceLine fence_line(std::string_view line)
{
    std::size_t offset = 0;
    while (offset < line.size()
           && (line[offset] == ' ' || line[offset] == '\t')) {
        ++offset;
    }

    const std::size_t tick_start = offset;
    while (offset < line.size() && line[offset] == '`') {
        ++offset;
    }
    if (offset - tick_start < 3) {
        return {};
    }

    const std::string_view suffix = line.substr(offset);
    std::size_t language_start = 0;
    while (language_start < suffix.size()
           && (suffix[language_start] == ' '
               || suffix[language_start] == '\t')) {
        ++language_start;
    }
    const std::string_view language = suffix.substr(language_start);
    const bool closes = language.empty();
    return FenceLine{
        .is_fence = true,
        .closes_fence = closes,
        .language = closes ? std::string{} : std::string{language},
    };
}

struct InlineLine {
    std::string text;
    bool bold{false};
    bool code{false};
};

[[nodiscard]]
InlineLine render_inline(std::string_view line)
{
    InlineLine result;
    std::size_t offset = 0;
    while (offset < line.size()) {
        if (line.substr(offset, 2) == "**") {
            const std::size_t end = line.find("**", offset + 2);
            if (end != std::string_view::npos) {
                result.text.append(line, offset + 2, end - offset - 2);
                result.bold = true;
                offset = end + 2;
                continue;
            }
        }
        if (line[offset] == '`') {
            const std::size_t end = line.find('`', offset + 1);
            if (end != std::string_view::npos) {
                result.text.append(line, offset + 1, end - offset - 1);
                result.code = true;
                offset = end + 1;
                continue;
            }
        }
        result.text.push_back(line[offset]);
        ++offset;
    }
    return result;
}

[[nodiscard]]
std::optional<std::string> heading_text(std::string_view line)
{
    std::size_t marker_end = 0;
    while (marker_end < line.size() && line[marker_end] == '#'
           && marker_end < 6) {
        ++marker_end;
    }
    if (marker_end == 0 || marker_end == line.size()
        || line[marker_end] != ' ') {
        return std::nullopt;
    }
    return std::string{line.substr(marker_end + 1)};
}

void append_markdown_line(
    std::vector<StyledLine>& lines,
    std::string_view line,
    bool in_code
)
{
    if (in_code) {
        lines.push_back(StyledLine{
            .text = "  " + std::string{line},
            .foreground = StyleColor::Secondary,
            .dim = true,
        });
        return;
    }

    if (const std::optional<std::string> heading = heading_text(line)) {
        lines.push_back(StyledLine{
            .text = *heading,
            .foreground = StyleColor::Accent,
            .bold = true,
        });
        return;
    }

    const InlineLine inline_line = render_inline(line);
    lines.push_back(StyledLine{
        .text = inline_line.text,
        .foreground = inline_line.code
            ? StyleColor::Accent
            : StyleColor::Default,
        .bold = inline_line.bold,
    });
}

[[nodiscard]]
std::vector<StyledLine> render_markdown_segment(std::string_view segment)
{
    std::vector<StyledLine> lines;
    bool in_code = false;
    std::size_t line_start = 0;
    while (line_start < segment.size()) {
        const std::size_t newline = segment.find('\n', line_start);
        const std::size_t line_end = newline == std::string_view::npos
            ? segment.size()
            : newline;
        const std::string_view line = segment.substr(
            line_start, line_end - line_start
        );
        const FenceLine fence = fence_line(line);
        if (in_code) {
            if (fence.is_fence && fence.closes_fence) {
                lines.push_back(StyledLine{
                    .text = "  [code]",
                    .foreground = StyleColor::Secondary,
                    .bold = true,
                });
                in_code = false;
            } else {
                append_markdown_line(lines, line, true);
            }
        } else if (fence.is_fence) {
            lines.push_back(StyledLine{
                .text = fence.language.empty()
                    ? "  [code]"
                    : "  [code: " + fence.language + "]",
                .foreground = StyleColor::Accent,
                .bold = true,
            });
            in_code = true;
        } else {
            append_markdown_line(lines, line, false);
        }

        if (newline == std::string_view::npos) {
            break;
        }
        line_start = newline + 1;
    }
    return lines;
}

[[nodiscard]]
std::vector<StyledLine> render_inline_segment(std::string_view segment)
{
    std::vector<StyledLine> lines;
    std::size_t line_start = 0;
    while (line_start < segment.size()) {
        const std::size_t newline = segment.find('\n', line_start);
        const std::size_t line_end = newline == std::string_view::npos
            ? segment.size()
            : newline;
        append_markdown_line(
            lines,
            segment.substr(line_start, line_end - line_start),
            false
        );
        if (newline == std::string_view::npos) {
            break;
        }
        line_start = newline + 1;
    }
    return lines;
}

[[nodiscard]]
std::vector<StyledLine> render_plain_segment(std::string_view segment)
{
    std::vector<StyledLine> lines;
    std::size_t line_start = 0;
    while (line_start < segment.size()) {
        const std::size_t newline = segment.find('\n', line_start);
        const std::size_t line_end = newline == std::string_view::npos
            ? segment.size()
            : newline;
        lines.push_back(StyledLine{
            .text = std::string{
                segment.substr(line_start, line_end - line_start)
            },
        });
        if (newline == std::string_view::npos) {
            break;
        }
        line_start = newline + 1;
    }
    return lines;
}

void append_lines(std::vector<StyledLine>& destination, std::vector<StyledLine> source)
{
    destination.insert(
        destination.end(),
        std::make_move_iterator(source.begin()),
        std::make_move_iterator(source.end())
    );
}

struct ToolStatusPresentation {
    std::string_view label;
    StyleColor color;
};

[[nodiscard]]
ToolStatusPresentation tool_status(const ToolCall& call) noexcept
{
    return std::visit(
        [](const auto& status) noexcept -> ToolStatusPresentation {
            using T = std::decay_t<decltype(status)>;
            if constexpr (std::is_same_v<T, ToolCall::Pending>) {
                return {"pending", StyleColor::Warning};
            } else if constexpr (std::is_same_v<T, ToolCall::Done>) {
                return {"done", StyleColor::Success};
            } else if constexpr (std::is_same_v<T, ToolCall::Failed>) {
                return {"failed", StyleColor::Error};
            } else {
                return {"rejected", StyleColor::Muted};
            }
        },
        call.status
    );
}

void append_tool_call(Frame& frame, const ToolCall& call)
{
    const ToolStatusPresentation presentation = tool_status(call);
    StyledLine header{
        .text = "+-- tool_call [" + std::string{presentation.label} + "] "
            + call.name,
        .foreground = presentation.color,
        .bold = true,
    };
    apply_turn_rail(header, Role::Assistant);
    frame.lines.push_back(std::move(header));
    StyledLine arguments{
        .text = "| args: " + call.args.dump(),
        .foreground = StyleColor::Muted,
        .dim = true,
    };
    apply_turn_rail(arguments, Role::Assistant);
    frame.lines.push_back(std::move(arguments));
    if (!call.is_pending()) {
        const std::string output = call.output().empty()
            ? "(empty)"
            : truncate_tool_output(call.output());
        StyledLine result{
            .text = "| output: " + output,
            .foreground = presentation.color,
        };
        apply_turn_rail(result, Role::Assistant);
        frame.lines.push_back(std::move(result));
    }
    StyledLine footer{
        .text = "+--",
        .foreground = presentation.color,
    };
    apply_turn_rail(footer, Role::Assistant);
    frame.lines.push_back(std::move(footer));
}

// 忙碌提示。Idle 返回空串表示「这一帧不需要状态行」—— 空闲时占一行反而是噪声。
// 提示必须不依赖已到达的文本：第一个 token 到达之前它就得在屏幕上，
// 否则用户分不清模型在想还是进程卡死了。
[[nodiscard]]
StatusPhase status_phase(const Model& model) noexcept
{
    return std::visit(
        [](const auto& value) noexcept -> StatusPhase {
            using T = std::decay_t<decltype(value)>;
            if constexpr (std::is_same_v<T, Streaming>) {
                return StatusPhase::Streaming;
            } else if constexpr (std::is_same_v<T, ExecutingTool>) {
                return StatusPhase::ExecutingTool;
            } else if constexpr (std::is_same_v<T, AwaitingPermission>) {
                return StatusPhase::AwaitingPermission;
            } else {
                return StatusPhase::Idle;
            }
        },
        model.phase
    );
}

[[nodiscard]]
std::string status_tool_name(const Model& model)
{
    return std::visit(
        [&model](const auto& value) -> std::string {
            using T = std::decay_t<decltype(value)>;
            if constexpr (std::is_same_v<T, ExecutingTool>) {
                return tool_name_for(model, value.id);
            } else if constexpr (std::is_same_v<T, AwaitingPermission>) {
                if (!model.pending_permission) {
                    return {};
                }
                return tool_name_for(model, model.pending_permission->id);
            } else {
                return {};
            }
        },
        model.phase
    );
}

[[nodiscard]]
bool has_status_metadata(const StatusBarInput& status) noexcept
{
    return !status.model_name.empty()
        || status.context_used.has_value()
        || status.context_limit.has_value()
        || status.tokens_per_second.has_value()
        || status.elapsed_seconds.has_value();
}

void append_projected_lines(
    Frame& frame,
    Role role,
    const std::vector<StyledLine>& lines
)
{
    for (const StyledLine& line : lines) {
        StyledLine projected = line;
        apply_turn_rail(projected, role);
        frame.lines.push_back(std::move(projected));
    }
}

void append_markdown_message(
    Frame& frame,
    const Message& message,
    std::size_t message_index,
    bool active_stream,
    MarkdownMessageState& state
)
{
    if (state.source.size() > message.text.size()
        || message.text.compare(0, state.source.size(), state.source) != 0) {
        state = MarkdownMessageState{};
    }
    state.source = message.text;

    static_cast<void>(markdown::scan(message.text, state.scanner));
    if (!active_stream) {
        static_cast<void>(markdown::finish(message.text, state.scanner));
    }

    const std::size_t committed_length = state.scanner.last_boundary;
    if (committed_length > state.committed_prefix.size()) {
        const std::string_view new_prefix = std::string_view{message.text}.substr(
            state.committed_prefix.size(),
            committed_length - state.committed_prefix.size()
        );
        append_lines(
            state.committed_lines,
            render_markdown_segment(new_prefix)
        );
        state.committed_prefix = message.text.substr(0, committed_length);
        ++state.committed_prefix_parse_count;
    }

    const std::string_view active_tail = std::string_view{message.text}.substr(
        committed_length
    );
    std::vector<StyledLine> active_lines;
    const bool pending_fence = state.scanner.line_prefix_is_fence
        && state.scanner.fence_tick_count >= 3;
    if (!active_tail.empty()) {
        if (state.scanner.in_fence || pending_fence) {
            active_lines = render_plain_segment(active_tail);
        } else {
            active_lines = render_inline_segment(active_tail);
        }
    }

    frame.markdown_layers.push_back(MarkdownLayer{
        .message_index = message_index,
        .committed_prefix = state.committed_prefix,
        .active_tail = std::string{active_tail},
    });
    append_projected_lines(frame, message.role, state.committed_lines);
    if (!active_lines.empty()) {
        append_projected_lines(
            frame,
            message.role,
            active_lines
        );
    }
}

}  // namespace

Frame view(const Model& model, const UiState& ui, Size size)
{
    MarkdownState markdown_state;
    return view(model, ui, size, markdown_state);
}

Frame view(
    const Model& model,
    const UiState& ui,
    Size size,
    MarkdownState& markdown_state
)
{
    Frame frame;
    markdown_state.messages.resize(model.thread.messages.size());
    const bool stream_active = std::holds_alternative<Streaming>(model.phase)
        && !model.thread.messages.empty();
    for (const Message& message : model.thread.messages) {
        const std::size_t message_index = static_cast<std::size_t>(
            &message - model.thread.messages.data()
        );
        const bool active_stream = stream_active
            && message_index + 1 == model.thread.messages.size()
            && message.role == Role::Assistant;
        if (!message.text.empty() && message.role == Role::Assistant) {
            append_markdown_message(
                frame,
                message,
                message_index,
                active_stream,
                markdown_state.messages.at(message_index)
            );
        } else if (!message.text.empty()) {
            std::vector<StyledLine> lines = render_plain_segment(message.text);
            append_projected_lines(frame, message.role, lines);
        }

        // 失败必须看得见。StreamError 把 phase 打回 Idle 并写下 error —— 状态行因此
        // 变空、正文可能一个字都没有，于是「回车之后什么都没发生」与卡死无从区分。
        // 跟在正文之后而不是替换它：流到一半才断的回合，已经吐出来的那半段仍然是
        // Keep failures attached to the turn rail while retaining the explicit
        // marker, so a partial response is not mistaken for normal prose.
        if (message.error) {
            StyledLine error{
                .text = "! " + *message.error,
                .foreground = StyleColor::Error,
            };
            apply_turn_rail(error, message.role);
            frame.lines.push_back(std::move(error));
        }
        for (const ToolCall& call : message.tool_calls) {
            append_tool_call(frame, call);
        }
    }

    StatusBarInput status = ui.status;
    status.phase = status_phase(model);
    status.tool_name = status_tool_name(model);
    status.permission_effect.clear();
    status.permission_args.clear();
    if (status.phase == StatusPhase::AwaitingPermission
        && model.pending_permission) {
        const ToolCall* call = tool_call_for(
            model, model.pending_permission->id
        );
        const std::string name = call
            ? call->name
            : model.pending_permission->id;
        const tool::ToolDef* definition = tool::find(name);
        status.permission_effect = definition
            ? effect_label(definition->effects)
            : "none";
        status.permission_args = call ? call->args.dump() : "{}";
    }
    if (status.phase == StatusPhase::AwaitingPermission
        && model.pending_permission) {
        frame.lines.push_back(StyledLine{
            .text = "permission: allow "
                + (status.tool_name.empty()
                    ? std::string{"tool"}
                    : status.tool_name)
                + "? effect="
                + (status.permission_effect.empty()
                    ? std::string{"none"}
                    : status.permission_effect)
                + " args: "
                + (status.permission_args.empty()
                    ? std::string{"{}"}
                    : status.permission_args)
                + " [y/n]",
            .rail = "!",
            .rail_foreground = StyleColor::Warning,
            .foreground = StyleColor::Warning,
            .bold = true,
        });
    }
    if (status.phase != StatusPhase::Idle || has_status_metadata(status)) {
        frame.status_bar = build_status_bar(status);
        frame.status_bar_line = frame.lines.size();
        frame.lines.push_back(StyledLine{
            .text = plain_status_text(*frame.status_bar),
            .foreground = StyleColor::Muted,
        });
    }

    const InputLayout input = layout_input(ui.input, ui.cursor, size.columns);
    for (const std::string& line : input.lines) {
        frame.lines.push_back(StyledLine{.text = line});
    }

    const int row_count = size.rows > 0 ? size.rows : 1;
    const std::size_t input_rows = input.lines.size();
    const std::size_t visible_input_rows = std::min<std::size_t>(
        input_rows, static_cast<std::size_t>(row_count)
    );
    const std::size_t first_visible_input_row = input_rows > visible_input_rows
        ? input_rows - visible_input_rows
        : 0;
    const std::size_t visible_cursor_line =
        input.cursor_line >= first_visible_input_row
        ? input.cursor_line - first_visible_input_row
        : 0;
    frame.cursor = CursorPosition{
        .row = row_count - static_cast<int>(visible_input_rows)
            + static_cast<int>(std::min<std::size_t>(
                visible_cursor_line, visible_input_rows - 1
            )),
        .column = input.cursor_column,
    };
    return frame;
}

}  // namespace my_agent::ui
