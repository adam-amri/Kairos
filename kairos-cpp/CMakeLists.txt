cmake_minimum_required(VERSION 3.20)
project(kairos_cpp VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

add_library(kairos INTERFACE)
target_include_directories(kairos INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_options(kairos INTERFACE
  $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic -Wno-psabi>)

# -ffast-math est PROSCRIT. Il autorise le compilateur a reordonner les
# operations flottantes et a supposer l'absence de NaN et d'infinis : le
# determinisme du moteur, et la precision du noyau mathematique, en dependent.
target_compile_options(kairos INTERFACE
  $<$<AND:$<CONFIG:Release>,$<CXX_COMPILER_ID:GNU,Clang>>:-O3>)

enable_testing()
add_executable(kairos_tests tests/test_main.cpp)
target_link_libraries(kairos_tests PRIVATE kairos)
target_include_directories(kairos_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests)
add_test(NAME kairos_tests COMMAND kairos_tests)

add_executable(kairos_bench bench/bench_main.cpp)
target_link_libraries(kairos_bench PRIVATE kairos)

add_executable(kairos_crossvalidate apps/crossvalidate.cpp)
target_link_libraries(kairos_crossvalidate PRIVATE kairos)
