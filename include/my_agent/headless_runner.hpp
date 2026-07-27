#pragma once
#include "my_agent/agent.hpp"
#include <functional>
#include <vector>

namespace my_agent{
    // 
    using EventSink = std::function<void(Msg)>;
    using StreamEffect = std::function<void(StartStream,EventSink)>;

    class HeadlessRunner{
    public:
        explicit HeadlessRunner(StreamEffect stream);

        // HeadlessRunner is thread-confined.
        // Call dispatch() sequentially from its owner thread.
        // StreamEffect must invoke EventSink synchronously before returning.
        [[nodiscard]]
        const Model& dispatch(Msg msg);
    
    private:
        void execute_cmd(NoCommand command);
        void execute_cmd(StartStream command);

    private:
        std::vector<Msg>    pending_msgs_;
        Model               current_model_{};
        StreamEffect        stream_;
    };
}