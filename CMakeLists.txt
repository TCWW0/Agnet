cmake_minimum_required(VERSION 4.4)
project (my_agent
    VERSION 0.0.1
    LANGUAGES CXX
)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

include(FetchContent)

FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG 52eb8108c5bdec04579160ae17225d66034bd723
)

set(JSON_BuildTests OFF CACHE INTERNAL "")
FetchContent_Declare(
    nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
    GIT_SHALLOW TRUE
)

# cpp-httplib 的 CMake 在找到 OpenSSL 时会以 INTERFACE 方式传播
# CPPHTTPLIB_OPENSSL_SUPPORT，我们不手动定义该宏。REQUIRE_OPENSSL 让缺少
# OpenSSL 时直接失败，而不是静默退化成没有 HTTPS 的构建。
set(HTTPLIB_REQUIRE_OPENSSL ON CACHE INTERNAL "")
set(HTTPLIB_TEST OFF CACHE INTERNAL "")
set(HTTPLIB_INSTALL OFF CACHE INTERNAL "")
FetchContent_Declare(
    httplib
    GIT_REPOSITORY https://github.com/yhirose/cpp-httplib.git
    GIT_TAG v0.52.0
    GIT_SHALLOW TRUE
)

if(MSVC)
    set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
endif()

FetchContent_MakeAvailable(googletest nlohmann_json httplib)

include(GoogleTest)

enable_testing()

find_package(Threads REQUIRED)

add_library(
    my_agent_tools
    src/tool/read.cpp
    src/tool/registry.cpp
)

target_include_directories(
    my_agent_tools
    PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

target_compile_features(
    my_agent_tools
    PUBLIC cxx_std_23
)

target_link_libraries(
    my_agent_tools
    PUBLIC nlohmann_json::nlohmann_json
)

# 传输层：httplib 只在 .cpp 内可见，头文件不泄漏 HTTP 库细节
add_library(
    my_agent_http
    src/http/http_client.cpp
)

target_include_directories(
    my_agent_http
    PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

target_compile_features(
    my_agent_http
    PUBLIC cxx_std_23
)

target_link_libraries(
    my_agent_http
    PUBLIC Threads::Threads
    PRIVATE httplib::httplib
)

add_executable(
    http_smoke_test
    tests/http_smoke_test.cpp
)

target_link_libraries(
    http_smoke_test
    PRIVATE
        my_agent_http
        GTest::gtest_main
)

gtest_discover_tests(
    http_smoke_test
    TEST_PREFIX "http_smoke."
)

add_library(
    my_agent_core
    src/domain/conversation.cpp
    src/runtime/agent.cpp
)

target_include_directories(
    my_agent_core
    PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

target_compile_features(
    my_agent_core
    PUBLIC cxx_std_23
)

target_link_libraries(
    my_agent_core
    PUBLIC my_agent_tools
)

add_executable(
    agent_loop_test
    tests/agent_loop_test.cpp
)

target_link_libraries(
    agent_loop_test
    PRIVATE
        my_agent_core
        GTest::gtest_main
)

gtest_discover_tests(
    agent_loop_test
    TEST_PREFIX "agent_loop."
)

add_library(
    my_agent_headless
    src/runtime/headless_runner.cpp
)

target_include_directories(
    my_agent_headless
    PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

target_compile_features(
    my_agent_headless
    PUBLIC cxx_std_23
)

target_link_libraries(
    my_agent_headless
    PUBLIC my_agent_core
)

add_executable(
    headless_runner_test
    tests/headless_runner_test.cpp
)

target_link_libraries(
    headless_runner_test
    PRIVATE
        my_agent_headless
        GTest::gtest_main
)

gtest_discover_tests(
    headless_runner_test
    TEST_PREFIX "headless_runner."
)

add_library(
    my_agent_async_runtime
    src/runtime/async_host.cpp
)

target_include_directories(
    my_agent_async_runtime
    PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

target_compile_features(
    my_agent_async_runtime
    PUBLIC cxx_std_23
)

target_link_libraries(
    my_agent_async_runtime
    PUBLIC
        my_agent_core
        Threads::Threads
)

add_executable(
    async_host_test
    tests/async_host_test.cpp
)

target_link_libraries(
    async_host_test
    PRIVATE
        my_agent_async_runtime
        GTest::gtest_main
)

gtest_discover_tests(
    async_host_test
    TEST_PREFIX "async_host."
)

add_executable(
    tool_loop_test
    tests/tool_loop_test.cpp
)

target_link_libraries(
    tool_loop_test
    PRIVATE
        my_agent_headless
        GTest::gtest_main
)

gtest_discover_tests(
    tool_loop_test
    TEST_PREFIX "tool_loop."
)

add_executable(
    tool_policy_test
    tests/tool_policy_test.cpp
)

target_link_libraries(
    tool_policy_test
    PRIVATE
        my_agent_tools
        GTest::gtest_main
)

gtest_discover_tests(
    tool_policy_test
    TEST_PREFIX "tool_policy."
)

add_executable(
    profile_test
    tests/profile_test.cpp
)

target_link_libraries(
    profile_test
    PRIVATE
        my_agent_core
        GTest::gtest_main
)

gtest_discover_tests(
    profile_test
    TEST_PREFIX "profile."
)

add_executable(
    read_tool_test
    tests/read_tool_test.cpp
)
target_link_libraries(
    read_tool_test
    PRIVATE
        my_agent_tools
        GTest::gtest_main
)
gtest_discover_tests(
    read_tool_test
    TEST_PREFIX "read_tool."
)
