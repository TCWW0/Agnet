cmake_minimum_required(VERSION 3.22)
project (my_agent
    VERSION 0.0.1
    LANGUAGES CXX
)

enable_testing()
add_executable(
    bootstrap_test
    tests/bootstrap_test.cpp
)

target_compile_features(
    bootstrap_test
    PRIVATE cxx_std_23
)

add_test(
    NAME boostrap
    COMMAND bootstrap_test
)