#pragma once

#include "my_agent/provider/provider.hpp"
#include "my_agent/runtime/agent.hpp"

#include <vector>

namespace my_agent{
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
        void execute_cmd(RunTool command);

    private:
        std::vector<Msg>    pending_msgs_;
        Model               current_model_{};
        StreamEffect        stream_;
    };
}
