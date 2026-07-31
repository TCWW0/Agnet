#include "my_agent/runtime/agent.hpp"

#include "my_agent/tool/tool.hpp"

#include <utility>
#include <variant>

namespace my_agent{
    namespace {
        Request make_request(const Thread& thread)
        {
            std::vector<ToolSpec> specs;
            specs.reserve(tool::registry().size());
            for (const tool::ToolDef& definition : tool::registry()) {
                specs.push_back(ToolSpec{
                    .name = definition.name,
                    .description = definition.description,
                    .input_schema = definition.input_schema,
                });
            }

            return Request{
                .messages = thread.messages,
                .tools = std::move(specs),
            };
        }

        /*
        * 对于一个apply函数，对应的期望是负责将被类型确定后的Msg往model其中的队列投递，并且保证对应model状态的正确转变
        */

        // 对于一个 Submit 类型的信息，对应的只需要将消息压到对应的队列中去并且更新一个流式传输状态即可
        Cmd apply(Model& model,const Submit& submit)
        {
            model.thread.messages.push_back(Message{
                .role = my_agent::Role::User,
                .text = submit.text,
            });

            Request request = make_request(model.thread);

            model.thread.messages.push_back(Message{
                .role = my_agent::Role::Assistant,
                .text = {}
            });
            model.phase = Streaming{};
            return StartStream{.request = std::move(request)};
        }

        Cmd apply(Model& model,const StreamTextDelta& delta)
        {
            my_agent::Thread& thread = model.thread;
            my_agent::Message& latest_msg = thread.messages.back();
            latest_msg.text += delta.text;
            return NoCommand{};
        }

        Cmd apply(Model& model,const StreamToolCall& event)
        {
            Message& assistant = model.thread.messages.back();
            assistant.tool_calls.push_back(ToolCall{
                .id = event.id,
                .name = event.name,
                .args = event.args,
            });
            return NoCommand{};
        }

        Cmd apply(Model& model,const StreamFinished&)
        {
            if (!model.thread.messages.empty()) {
                Message& assistant = model.thread.messages.back();
                for (ToolCall& tool_call : assistant.tool_calls) {
                    if (tool_call.is_pending()) {
                        return RunTool{
                            .id = tool_call.id,
                            .name = tool_call.name,
                            .args = tool_call.args,
                        };
                    }
                }
            }
            model.phase = my_agent::Idle{};
            return NoCommand{};
        }

        Cmd apply(Model& model,const StreamError& err)
        {
            model.phase = my_agent::Idle{};
            my_agent::Message& latest_msg = model.thread.messages.back();
            latest_msg.error = err.message;
            return NoCommand{};
        }

        Cmd apply(Model& model,const ToolExecOutput& event)
        {
            Message* matched_message = nullptr;
            ToolCall* matched_call = nullptr;
            for (auto message_it = model.thread.messages.rbegin();
                message_it != model.thread.messages.rend(); ++message_it) {
                for (auto call_it = message_it->tool_calls.rbegin();
                    call_it != message_it->tool_calls.rend(); ++call_it) {
                    if (call_it->id == event.id) {
                        matched_message = &*message_it;
                        matched_call = &*call_it;
                        break;
                    }
                }
                if (matched_call != nullptr) {
                    break;
                }
            }

            if (matched_call == nullptr) {
                return NoCommand{};
            }

            if (event.result) {
                matched_call->status = ToolCall::Done{
                    .output = event.result->text,
                };
            } else {
                matched_call->status = ToolCall::Failed{
                    .output = event.result.error().render(),
                };
            }

            for (ToolCall& tool_call : matched_message->tool_calls) {
                if (tool_call.is_pending()) {
                    return RunTool{
                        .id = tool_call.id,
                        .name = tool_call.name,
                        .args = tool_call.args,
                    };
                }
            }

            Request request = make_request(model.thread);
            model.thread.messages.push_back(Message{
                .role = Role::Assistant,
                .text = {},
            });
            model.phase = Streaming{};
            return StartStream{.request = std::move(request)};
        }

        Cmd apply(Model& model,const SetProfile& event)
        {
            model.profile = event.profile;
            return NoCommand{};
        }
    }

    Step update(Model model,Msg msg)
    {
        Cmd cmd = std::visit(
            [&model](const auto& event) -> Cmd{
                return apply(model,event);
            },
            msg
        );
        return Step{
            .model = std::move(model),
            .cmd = std::move(cmd),
        };
    }
}
