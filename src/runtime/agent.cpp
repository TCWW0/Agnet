#include "my_agent/runtime/agent.hpp"

#include "my_agent/domain/conversation.hpp"
#include "my_agent/provider/provider.hpp"
#include "my_agent/runtime/model.hpp"
#include "my_agent/runtime/msg.hpp"
#include "my_agent/tool/policy.hpp"
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

        Cmd kick_pending_tools(Model& model)
        {
            if (model.thread.messages.empty()){
                model.phase = Idle{};
                return NoCommand{};
            }

            Message& assistant = model.thread.messages.back();

            for (ToolCall& tool_call : assistant.tool_calls) {
                if (!tool_call.is_pending()) {
                    continue;
                }

                const tool::ToolDef* definition = tool::find(tool_call.name);
                const bool needs_permission = definition != nullptr
                    && tool::policy::permission(
                        definition->effects,
                        model.profile
                    ) == tool::policy::Decision::Prompt;

                if (needs_permission) {
                    model.pending_permission = PendingPermission{
                        .id = tool_call.id,
                    };
                    model.phase = AwaitingPermission{};
                    return NoCommand{};
                }

                model.phase = ExecutingTool{
                    .id = tool_call.id,
                };
                return RunTool{
                    .id = tool_call.id,
                    .name = tool_call.name,
                    .args = tool_call.args,
                };
            }

            if (assistant.tool_calls.empty()) {
                model.phase = Idle{};
                return NoCommand{};
            }

            Request request = make_request(model.thread);
            model.thread.messages.push_back(Message{
                .role = Role::Assistant,
                .text = {},
            });
            model.phase = Streaming{};
            return StartStream{.request = std::move(request)};
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
            if (!std::holds_alternative<Streaming>(model.phase)) {
                return NoCommand{};
            }
            return kick_pending_tools(model);
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
            ToolCall* matched_call = nullptr;
            for (auto message_it = model.thread.messages.rbegin();
                message_it != model.thread.messages.rend(); ++message_it) {
                for (auto call_it = message_it->tool_calls.rbegin();
                    call_it != message_it->tool_calls.rend(); ++call_it) {
                    if (call_it->id == event.id) {
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
            return kick_pending_tools(model);
        }

        Cmd apply(Model& model,const SetProfile& event)
        {
            model.profile = event.profile;
            return NoCommand{};
        }

        Cmd apply(Model& model,const PermissionApprove& event)
        {
            if (!std::holds_alternative<AwaitingPermission>(model.phase)
                || !model.pending_permission
                || model.pending_permission->id != event.id
                || model.thread.messages.empty()) {
                return NoCommand{};
            }

            Message& assistant = model.thread.messages.back();
            if (assistant.role != Role::Assistant) {
                return NoCommand{};
            }

            for (ToolCall& toolcall : assistant.tool_calls) {
                if (toolcall.id != event.id || !toolcall.is_pending()) {
                    continue;
                }

                RunTool command{
                    .id = toolcall.id,
                    .name = toolcall.name,
                    .args = toolcall.args,
                };

                model.pending_permission.reset();
                model.phase = ExecutingTool{
                    .id = toolcall.id,
                };

                return command;
            }
            return NoCommand{};
        }

        Cmd apply(Model& model,const PermissionReject& event)
        {
            if (!std::holds_alternative<AwaitingPermission>(model.phase)
                || !model.pending_permission
                || model.pending_permission->id != event.id
                || model.thread.messages.empty()) {
                return NoCommand{};
            }
            Message& assistant = model.thread.messages.back();
            if (assistant.role != Role::Assistant) {
                return NoCommand{};
            }
            for (ToolCall& toolcall : assistant.tool_calls) {
                if (toolcall.id != event.id || !toolcall.is_pending()) {
                    continue;
                }

                std::string output{"User rejected this tool call."};

                if (event.feedback && !event.feedback->empty()) {
                    output += " Feedback: ";
                    output += *event.feedback;
                }

                toolcall.status = ToolCall::Rejected{
                    .output = std::move(output),
                };

                model.pending_permission.reset();
            }
            return kick_pending_tools(model);
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
