#pragma once
#include <cstdint>
namespace my_agent{
    enum class Profile:std::uint8_t{
        Write,
        Ask,
        Minimal,
    };

    static_assert(
        static_cast<std::uint8_t>(Profile::Write) == 0,
        "Profile::Write must remain the default profile");

} // namespace my_agent
