#pragma once

#include <cstdint>
#include <initializer_list>

namespace my_agent::tool{
    enum class Effect : std::uint8_t {
        ReadFs  = 1u<<0,
        WriteFs = 1u<<1,
        Net     = 1u<<2,
        Exec    = 1u<<3,
    };

    class EffectSet{
    public:
        constexpr EffectSet() noexcept = default;

        constexpr EffectSet(std::initializer_list<Effect> effects) noexcept
        {
            for(Effect effect:effects){
                bits_ |= static_cast<std::uint8_t>(effect);
            }
        }

        [[nodiscard]]
        constexpr bool has(Effect effect) const noexcept
        {
            return (bits_ & static_cast<std::uint8_t>(effect))!=0;
        }
    private:
        std::uint8_t bits_{0};
    };
}//namespace my_agent::tool