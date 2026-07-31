#pragma once
#include "my_agent/domain/profile.hpp"
#include "my_agent/tool/effects.hpp"

#include <cstdint>

namespace my_agent::tool::policy{
    enum class Decision : std::uint8_t {
        Allow,
        Prompt,
    };

    [[nodiscard]]
    constexpr Decision permission(EffectSet effects,Profile profile) noexcept
    {
        if (profile == Profile::Write){
            return Decision::Allow;
        }
        if(effects.has(Effect::WriteFs)||effects.has(Effect::Net)){
            return Decision::Prompt;
        }
        if (effects.has(Effect::Exec)){
            return Decision::Prompt;
        }
        if (profile == Profile::Minimal && effects.has(Effect::ReadFs)){
            return Decision::Prompt;
        }
        return Decision::Allow;
    }
} // namespace my_agent::tool::policy
