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
set(SMTG_CREATE_MODULE_INFO OFF CACHE BOOL "" FORCE)

include(cmake/M3Vst3Sdk.cmake)
m3_add_pinned_vst3_sdk()
include(cmake/M3CompilerOptions.cmake)

find_package(Threads REQUIRED)
enable_testing()

# Steinberg's package helper uses this variable to attach the platform module
# entry source. The SDK sets it only in its subdirectory scope.
set(public_sdk_SOURCE_DIR "${M3_VST3_SDK_ROOT}/public.sdk")

set(M3_NATIVE_CORE_SOURCES
    native/src/generated_note_ledger.cpp
    native/src/parameter_contract.cpp
    native/src/state_image.cpp
)

set(M3_NATIVE_SHARED_ADAPTER_SOURCES
    native/plugin/prepared_config_exchange.cpp
)

set(M3_NATIVE_PLUGIN_SOURCES
    native/plugin/clap_adapter.cpp
    native/plugin/clap_entry.cpp
    native/plugin/clap_parameter_bridge.cpp
    native/plugin/clap_state_stream.cpp
    native/plugin/midi_pipeline.cpp
    native/plugin/parameter_contract.cpp
    native/plugin/probe_processor.cpp
    native/plugin/state_codec.cpp
)

set(M3_VST3_ADAPTER_SOURCES
    native/vst3/vst3_component.cpp
    native/vst3/vst3_event_sink.cpp
    native/vst3/vst3_factory.cpp
    native/vst3/vst3_parameter_bridge.cpp
    native/vst3/vst3_state_stream.cpp
    third_party/vst3sdk/public.sdk/source/vst/vstsinglecomponenteffect.cpp
)

set(M3_NATIVE_TEST_SOURCES
    native/tests/fake_clap_host.cpp
    native/tests/fake_vst3_host.cpp
    native/tests/test_clap_lifecycle.cpp
    native/tests/test_fixed_vector.cpp
    native/tests/test_generated_note_ledger.cpp
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
    native/tests/test_vst3_audio.cpp
    native/tests/test_vst3_events.cpp
    native/tests/test_vst3_factory.cpp
    native/tests/test_vst3_lifecycle.cpp
    native/tests/test_vst3_parameters.cpp
    native/tests/test_vst3_processing.cpp
    native/tests/test_vst3_reconfiguration.cpp
    native/tests/test_vst3_setup.cpp
    native/tests/test_vst3_state.cpp
)

add_executable(m3_native_tests
    ${M3_NATIVE_CORE_SOURCES}
    ${M3_NATIVE_SHARED_ADAPTER_SOURCES}
    ${M3_NATIVE_PLUGIN_SOURCES}
    ${M3_VST3_ADAPTER_SOURCES}
    ${M3_NATIVE_TEST_SOURCES}
)
target_compile_definitions(m3_native_tests PRIVATE M3_TESTING)
target_include_directories(m3_native_tests PRIVATE
    native/include
    native/plugin
    native/vst3
    third_party/clap/include
)
target_include_directories(m3_native_tests SYSTEM BEFORE PRIVATE
    third_party/vst3sdk
)
target_link_libraries(m3_native_tests PRIVATE Threads::Threads sdk m)
m3_apply_project_options(m3_native_tests)
add_test(NAME m3_native_tests COMMAND m3_native_tests)

set(M3_CLAP_HISTORY_SOURCES
    native/plugin/clap_adapter.cpp
    native/plugin/clap_entry.cpp
    native/plugin/clap_parameter_bridge.cpp
    native/plugin/clap_state_stream.cpp
    native/plugin/midi_pipeline.cpp
    native/plugin/parameter_contract.cpp
    native/plugin/state_codec.cpp
)

add_library(m3_clap_history MODULE EXCLUDE_FROM_ALL
    ${M3_NATIVE_CORE_SOURCES}
    ${M3_NATIVE_SHARED_ADAPTER_SOURCES}
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

smtg_add_vst3plugin(m3_vst3_probe
    PACKAGE_NAME "M3_Polyphonic_Audio_to_MIDI_Probe"
    SOURCES_LIST
        ${M3_NATIVE_CORE_SOURCES}
        ${M3_NATIVE_SHARED_ADAPTER_SOURCES}
        ${M3_VST3_ADAPTER_SOURCES}
)
target_compile_definitions(m3_vst3_probe PRIVATE M3_VST3_PROBE_BUILD)
target_include_directories(m3_vst3_probe PRIVATE
    native/include
    native/plugin
    native/vst3
)
target_include_directories(m3_vst3_probe SYSTEM BEFORE PRIVATE
    third_party/vst3sdk
)
target_link_libraries(m3_vst3_probe PRIVATE Threads::Threads sdk m)
m3_apply_project_options(m3_vst3_probe)
set_target_properties(m3_vst3_probe PROPERTIES EXCLUDE_FROM_ALL TRUE)

# Later tasks replace these remaining reservations with concrete targets.
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
