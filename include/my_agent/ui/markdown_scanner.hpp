#pragma once

#include <cstddef>
#include <string_view>
#include <vector>

namespace my_agent::ui::markdown {

struct ScanState {
    std::size_t scan_position{0};
    bool in_fence{false};
    bool fence_safe_to_commit{true};
    std::size_t last_boundary{0};

    std::size_t line_start{0};
    std::size_t fence_tick_count{0};
    bool line_prefix_is_fence{true};
    bool line_after_ticks{false};
    bool line_has_non_whitespace_after_ticks{false};
};

struct ScanResult {
    std::size_t committed_prefix_length{0};
    std::vector<std::size_t> newly_committed_boundaries;
};

[[nodiscard]]
ScanResult scan(std::string_view accumulated, ScanState& state);

[[nodiscard]]
ScanResult finish(std::string_view accumulated, ScanState& state);

}  // namespace my_agent::ui::markdown
