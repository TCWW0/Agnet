#include "read.hpp"
#include "my_agent/tool/effects.hpp"
#include "my_agent/tool/tool.hpp"
#include "nlohmann/json_fwd.hpp"

#include <expected>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <utility>
#include <string_view>
#include <system_error>

namespace my_agent::tool::detail{
    namespace {
    namespace fs = std::filesystem;

        // 调用者应该尽量保持传入的路径本身已经被规范化，这样能够保持整体的判断更加合理
        [[nodiscard]]
        bool is_within_workspace(const fs::path& normalized_root,const fs::path& normalized_target)
        {
            auto root_part = normalized_root.begin();
            auto target_part = normalized_target.begin();

            for(;root_part != normalized_root.end() && target_part !=normalized_target.end();++root_part,++target_part){
                if(*root_part != *target_part){
                    return false;
                }
            }
            return root_part ==normalized_root.end();
        }

        [[nodiscard]]
        std::expected<fs::path, ToolError> resolve_read_path(const fs::path& workspace_root,std::string_view raw_path)
        {
            fs::path requested{raw_path};

            if (requested.is_relative()){
                requested = workspace_root/raw_path;
            }

            std::error_code error;
            fs::path target = fs::weakly_canonical(requested,error);

            if(error || target.empty()) {
                return std::unexpected(ToolError{
                    .kind = ErrorKind::OutOfWorkspace,
                    .message = "read could not prove path is within woekspace: "
                    + requested.string()
                    + " (workspace: "
                    + workspace_root.string()
                    + ")",
                });
            }

            if (!is_within_workspace(workspace_root, target)){
                return std::unexpected(ToolError{
                    .kind = ErrorKind::OutOfWorkspace,
                    .message =
                        "read refused path outside workspace: "
                        +target.string()
                        +" (workspace: "
                        + workspace_root.string()
                        +")",
                });
            }
            return target;
        }

        ExecResult execute_read (const fs::path& workspace_root,const nlohmann::json& args)
        {
            if (!args.is_object()
                || !args.contains("path")
                || !args["path"].is_string()){
                    return std::unexpected(ToolError{
                        .kind = ErrorKind::InvalidArgs,
                        .message = "read requires a string path",
                    });
            }

            const std::string raw_path = args["path"].get<std::string>();
            if (raw_path.empty()){
                return std::unexpected(ToolError{
                    .kind = ErrorKind::InvalidArgs,
                    .message = "read path must not be empty",
                });
            }

            const auto path = resolve_read_path(workspace_root,raw_path);
            if (!path){
                return std::unexpected(path.error());
            }

            std::ifstream input{*path,std::ios::binary};
            if(!input) {
                return std::unexpected{ToolError{
                    .kind = ErrorKind::NotFound,
                    .message = "unable to open file: "+path->string(),
                }};
            }

            std::string content {
                std::istreambuf_iterator<char>{input},
                std::istreambuf_iterator<char>{}
            };
            return ToolOutput{.text = std::move(content)};
        }
    }   //namespace

    ToolDef make_read_tool(std::filesystem::path workspace_root)
    {
        return ToolDef{
            .name = "read",
            .description = "Read a text file from the current workspace",
            .input_schema = nlohmann::json{
                {"type","object"},
                {"properties",nlohmann::json{
                    {"path",nlohmann::json{
                        {"type","string"},
                        {"minLength",1},
                    }},
                }},
                {"required",nlohmann::json::array({"path"})},
                {"additionalProperties",false},
            },
            .effects = {Effect::ReadFs},
            .execute = [workspace_root = std::move(workspace_root)](const nlohmann::json& args){
                return execute_read(workspace_root, args);
            },
        };
    }
}
