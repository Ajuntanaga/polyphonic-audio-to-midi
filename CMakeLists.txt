cmake_minimum_required(VERSION 3.25)

project(M3PolyphonicAudioToMIDI VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(M3_PROJECT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}")

option(M3_ENABLE_ASAN_UBSAN "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
option(M3_ENABLE_TSAN "Enable ThreadSanitizer" OFF)
if(M3_ENABLE_ASAN_UBSAN AND M3_ENABLE_TSAN)
    message(FATAL_ERROR "ASan/UBSan and TSan builds must remain separate")
endif()

set(SMTG_ENABLE_VSTGUI_SUPPORT OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_PLUGIN_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_HOSTING_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_ADD_VST3_UTILITIES OFF CACHE BOOL "" FORCE)
set(SMTG_CREATE_PLUGIN_LINK OFF CACHE BOOL "" FORCE)
set(SMTG_RUN_VST_VALIDATOR OFF CACHE BOOL "" FORCE)

include(cmake/M3Vst3Sdk.cmake)
m3_add_pinned_vst3_sdk()
include(cmake/M3CompilerOptions.cmake)

find_package(Threads REQUIRED)
enable_testing()

set(M3_NATIVE_CORE_SOURCES
    native/src/parameter_contract.cpp
    native/src/state_image.cpp
)

set(M3_NATIVE_PLUGIN_SOURCES
    native/plugin/clap_adapter.cpp
    native/plugin/clap_entry.cpp
    native/plugin/clap_parameter_bridge.cpp
    native/plugin/clap_state_stream.cpp
    native/plugin/midi_pipeline.cpp
    native/plugin/parameter_contract.cpp
    native/plugin/prepared_config_exchange.cpp
    native/plugin/probe_processor.cpp
    native/plugin/state_codec.cpp
)

set(M3_NATIVE_TEST_SOURCES
    native/tests/fake_clap_host.cpp
    native/tests/test_clap_lifecycle.cpp
    native/tests/test_fixed_vector.cpp
    native/tests/test_main.cpp
    native/tests/test_midi_pipeline.cpp
    native/tests/test_parameter_contract.cpp
    native/tests/test_parameter_normalization.cpp
    native/tests/test_pitch_math.cpp
    native/tests/test_prepared_config_exchange.cpp
    native/tests/test_probe_processor.cpp
    native/tests/test_state_codec.cpp
    native/tests/test_state_image.cpp
    native/tests/test_support.cpp
    native/tests/test_test_support.cpp
)

add_executable(m3_native_tests
    ${M3_NATIVE_CORE_SOURCES}
    ${M3_NATIVE_PLUGIN_SOURCES}
    ${M3_NATIVE_TEST_SOURCES}
)
target_compile_definitions(m3_native_tests PRIVATE M3_TESTING)
target_include_directories(m3_native_tests PRIVATE
    native/include
    native/plugin
    third_party/clap/include
)
target_link_libraries(m3_native_tests PRIVATE Threads::Threads m)
m3_apply_project_options(m3_native_tests)
add_test(NAME m3_native_tests COMMAND m3_native_tests)

set(M3_CLAP_HISTORY_SOURCES
    native/plugin/clap_adapter.cpp
    native/plugin/clap_entry.cpp
    native/plugin/clap_parameter_bridge.cpp
    native/plugin/clap_state_stream.cpp
    native/plugin/midi_pipeline.cpp
    native/plugin/parameter_contract.cpp
    native/plugin/prepared_config_exchange.cpp
    native/plugin/state_codec.cpp
)

add_library(m3_clap_history MODULE EXCLUDE_FROM_ALL
    ${M3_NATIVE_CORE_SOURCES}
    ${M3_CLAP_HISTORY_SOURCES}
)
target_include_directories(m3_clap_history PRIVATE
    native/include
    native/plugin
    third_party/clap/include
)
target_link_libraries(m3_clap_history PRIVATE Threads::Threads m)
m3_apply_project_options(m3_clap_history)
set_target_properties(m3_clap_history PROPERTIES
    PREFIX ""
    SUFFIX ".clap"
    OUTPUT_NAME "M3_Polyphonic_Audio_to_MIDI_Historical"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/clap"
)

# Tasks 8 onward replace these reservations with concrete, SDK-backed targets.
# Keeping the names present now makes the guarded build interface stable without
# claiming that a VST3 artifact exists during the build-foundation task.
add_custom_target(m3_vst3_probe
    COMMAND ${CMAKE_COMMAND} -E echo "m3_vst3_probe is reserved for Task 13"
    VERBATIM
)
add_custom_target(m3_vst3_production
    COMMAND ${CMAKE_COMMAND} -E echo "m3_vst3_production is reserved for Task 18"
    VERBATIM
)
add_custom_target(m3_vst3_benchmark
    COMMAND ${CMAKE_COMMAND} -E echo "m3_vst3_benchmark is reserved for Task 20"
    VERBATIM
)
add_custom_target(m3_validate_production
    COMMAND ${CMAKE_COMMAND} -E echo "m3_validate_production is reserved for Task 21"
    VERBATIM
)
