#include "my_agent/tool/tool.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <utility>

#include <gtest/gtest.h>
#include <nlohmann/json.hpp>

namespace {

namespace fs = std::filesystem;

class ScopedDirectory {
public:
    explicit ScopedDirectory(const fs::path& parent)
    {
        const auto nonce =
            std::chrono::steady_clock::now().time_since_epoch().count();

        for (unsigned int attempt = 0; attempt < 100; ++attempt) {
            path_ = parent / (
                "my_agent_read_tool_fixture_"
                + std::to_string(nonce)
                + "_"
                + std::to_string(attempt)
            );

            std::error_code error;
            if (fs::create_directory(path_, error)) {
                return;
            }
            if (error && error != std::errc::file_exists) {
                throw std::runtime_error{
                    "failed to create read tool fixture directory: "
                    + error.message()
                };
            }
        }

        throw std::runtime_error{
            "failed to create a unique read tool fixture directory"
        };
    }

    ~ScopedDirectory()
    {
        std::error_code error;
        fs::remove_all(path_, error);
    }

    ScopedDirectory(const ScopedDirectory&) = delete;
    ScopedDirectory& operator=(const ScopedDirectory&) = delete;

    [[nodiscard]] const fs::path& path() const noexcept
    {
        return path_;
    }

private:
    fs::path path_;
};

class ScopedTextFile {
public:
    ScopedTextFile(fs::path path, const std::string& content)
        : path_(std::move(path))
    {
        if (fs::exists(path_)) {
            throw std::runtime_error{"read tool fixture already exists"};
        }

        std::ofstream output{path_, std::ios::binary | std::ios::trunc};
        if (!output) {
            throw std::runtime_error{"failed to create read tool fixture"};
        }

        output << content;
        if (!output) {
            std::error_code error;
            fs::remove(path_, error);
            throw std::runtime_error{"failed to write read tool fixture"};
        }
    }

    ~ScopedTextFile()
    {
        std::error_code error;
        fs::remove(path_, error);
    }

    ScopedTextFile(const ScopedTextFile&) = delete;
    ScopedTextFile& operator=(const ScopedTextFile&) = delete;

    [[nodiscard]] const fs::path& path() const noexcept
    {
        return path_;
    }

private:
    fs::path path_;
};

} // namespace

TEST(ReadToolTest, RegisteredReadToolReadsSmallTextFileInsideWorkspace)
{
    ScopedDirectory fixture_directory{fs::current_path()};
    ScopedTextFile fixture{
        fixture_directory.path() / "inside.txt",
        "alpha\nbeta\n"
    };

    const auto* read = my_agent::tool::find("read");
    ASSERT_NE(nullptr, read);
    EXPECT_TRUE(read->effects.has(my_agent::tool::Effect::ReadFs));

    const auto result = my_agent::tool::execute(
        "read",
        nlohmann::json{{
            "path",
            fixture.path().lexically_relative(fs::current_path()).string(),
        }}
    );

    ASSERT_TRUE(result.has_value()) << result.error().render();
    EXPECT_EQ("alpha\nbeta\n", result->text);
}

TEST(ReadToolTest, RejectsExistingFileOutsideWorkspace)
{
    const fs::path workspace_root = fs::canonical(fs::current_path());
    const fs::path outside_directory = workspace_root.parent_path();
    ASSERT_NE(workspace_root, outside_directory);

    ScopedDirectory fixture_directory{outside_directory};
    ScopedTextFile fixture{
        fixture_directory.path() / "outside.txt",
        "outside workspace content\n"
    };

    const auto result = my_agent::tool::execute(
        "read",
        nlohmann::json{{"path", fixture.path().string()}}
    );

    ASSERT_FALSE(result.has_value());
    EXPECT_EQ(
        my_agent::tool::ErrorKind::OutOfWorkspace,
        result.error().kind
    );
}

TEST(ReadToolTest, RejectsMissingPathOutsideWorkspace)
{
    const fs::path workspace_root = fs::canonical(fs::current_path());
    const fs::path outside_directory = workspace_root.parent_path();
    ASSERT_NE(workspace_root, outside_directory);

    ScopedDirectory fixture_directory{outside_directory};
    const fs::path missing_path = fixture_directory.path() / "missing.txt";
    ASSERT_FALSE(fs::exists(missing_path));

    const auto result = my_agent::tool::execute(
        "read",
        nlohmann::json{{"path", missing_path.string()}}
    );

    ASSERT_FALSE(result.has_value());
    EXPECT_EQ(
        my_agent::tool::ErrorKind::OutOfWorkspace,
        result.error().kind
    );
}
