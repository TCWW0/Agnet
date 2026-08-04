#include "my_agent/ui/markdown_scanner.hpp"

#include <cstddef>

namespace my_agent::ui::markdown {

namespace {

[[nodiscard]]
bool is_horizontal_whitespace(unsigned char byte) noexcept
{
    return byte == ' ' || byte == '\t' || byte == '\r';
}

void reset_line(ScanState& state) noexcept
{
    state.line_start = state.scan_position;
    state.fence_tick_count = 0;
    state.line_prefix_is_fence = true;
    state.line_after_ticks = false;
    state.line_has_non_whitespace_after_ticks = false;
}

void observe_line_byte(ScanState& state, unsigned char byte) noexcept
{
    if (!state.line_prefix_is_fence) {
        return;
    }

    if (state.fence_tick_count == 0) {
        if (is_horizontal_whitespace(byte)) {
            return;
        }
        if (byte == '`') {
            state.fence_tick_count = 1;
            return;
        }
        state.line_prefix_is_fence = false;
        return;
    }

    if (!state.line_after_ticks) {
        if (byte == '`') {
            ++state.fence_tick_count;
            return;
        }
        state.line_after_ticks = true;
    }

    if (!is_horizontal_whitespace(byte)) {
        state.line_has_non_whitespace_after_ticks = true;
    }
}

void commit_boundary(ScanState& state, ScanResult& result, std::size_t boundary)
{
    if (boundary <= state.last_boundary) {
        return;
    }
    state.last_boundary = boundary;
    result.newly_committed_boundaries.push_back(boundary);
}

void finish_line(
    ScanState& state,
    ScanResult& result,
    std::size_t boundary
)
{
    const bool is_fence_line = state.line_prefix_is_fence
        && state.fence_tick_count >= 3;
    const bool closes_fence = is_fence_line
        && !state.line_has_non_whitespace_after_ticks;

    if (state.in_fence) {
        if (closes_fence) {
            state.in_fence = false;
            state.fence_safe_to_commit = true;
            commit_boundary(state, result, boundary);
        }
    } else if (is_fence_line) {
        state.in_fence = true;
        state.fence_safe_to_commit = false;
    } else {
        state.fence_safe_to_commit = true;
        commit_boundary(state, result, boundary);
    }
}

}  // namespace

ScanResult scan(std::string_view accumulated, ScanState& state)
{
    if (state.scan_position > accumulated.size()) {
        state = ScanState{};
    }

    ScanResult result;
    result.committed_prefix_length = state.last_boundary;

    while (state.scan_position < accumulated.size()) {
        const unsigned char byte = static_cast<unsigned char>(
            accumulated[state.scan_position]
        );
        if (byte == '\n') {
            const bool is_fence_line = state.line_prefix_is_fence
                && state.fence_tick_count >= 3;
            const bool closes_fence = is_fence_line
                && !state.line_has_non_whitespace_after_ticks;
            const bool opens_fence = is_fence_line;
            const std::size_t boundary = state.scan_position + 1;

            if (state.in_fence) {
                if (closes_fence) {
                    state.in_fence = false;
                    state.fence_safe_to_commit = true;
                    state.last_boundary = boundary;
                    result.newly_committed_boundaries.push_back(boundary);
                }
            } else if (opens_fence) {
                state.in_fence = true;
                state.fence_safe_to_commit = false;
            } else {
                state.fence_safe_to_commit = true;
                state.last_boundary = boundary;
                result.newly_committed_boundaries.push_back(boundary);
            }

            ++state.scan_position;
            reset_line(state);
            continue;
        }

        observe_line_byte(state, byte);
        ++state.scan_position;
    }

    result.committed_prefix_length = state.last_boundary;
    return result;
}

ScanResult finish(std::string_view accumulated, ScanState& state)
{
    if (state.scan_position > accumulated.size()) {
        state = ScanState{};
    }

    static_cast<void>(scan(accumulated, state));
    ScanResult result;
    result.committed_prefix_length = state.last_boundary;
    if (state.scan_position == accumulated.size()
        && state.line_start < accumulated.size()) {
        finish_line(state, result, accumulated.size());
        state.scan_position = accumulated.size();
        reset_line(state);
    }
    result.committed_prefix_length = state.last_boundary;
    return result;
}

}  // namespace my_agent::ui::markdown
