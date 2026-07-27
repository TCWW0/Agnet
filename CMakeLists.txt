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

if(MSVC)
    set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
endif()

FetchContent_MakeAvailable(googletest)

include(GoogleTest)

enable_testing()

add_library(
    my_agent_core
    src/agent.cpp
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
    src/headless_runner.cpp
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