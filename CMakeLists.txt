cmake_minimum_required(VERSION 4.4)
project (my_agent
    VERSION 0.0.1
    LANGUAGES CXX
)

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
    PRIVATE my_agent_core
)

add_test(
    NAME agent_loop
    COMMAND agent_loop_test
)