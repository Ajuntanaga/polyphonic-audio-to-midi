NATIVE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT := $(abspath $(NATIVE_DIR)/..)
BUILD_DIR ?= $(ROOT)/build/native
CXX ?= g++

COMMON_CPPFLAGS := -I$(NATIVE_DIR)/include -I$(NATIVE_DIR)/plugin -I$(ROOT)/third_party/clap/include
COMMON_CXXFLAGS := -std=c++17 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
	-fno-exceptions -fno-rtti -fstack-protector-strong \
	-ffile-prefix-map=$(ROOT)=. -fmacro-prefix-map=$(ROOT)=.
TEST_CXXFLAGS := $(COMMON_CXXFLAGS) -O0 -g3 -DM3_TESTING
SANITIZE_CXXFLAGS := $(COMMON_CXXFLAGS) -O1 -g3 -DM3_TESTING \
	-fsanitize=address,undefined -fno-omit-frame-pointer
TSAN_CXXFLAGS := $(COMMON_CXXFLAGS) -O1 -g3 -DM3_TESTING \
	-fsanitize=thread -fno-omit-frame-pointer
PRODUCTION_CXXFLAGS := $(COMMON_CXXFLAGS) -O3 -DNDEBUG -fPIC -fvisibility=hidden
PROBE_CXXFLAGS := $(PRODUCTION_CXXFLAGS) -DM3_PROBE_BUILD
SHARED_LDFLAGS := -shared -Wl,-z,relro,-z,now -Wl,--no-undefined -Wl,--build-id=none

CORE_SOURCES := $(sort $(wildcard $(NATIVE_DIR)/src/*.cpp))
TEST_SOURCES := $(sort $(wildcard $(NATIVE_DIR)/tests/*.cpp))
PLUGIN_SOURCES := $(sort $(wildcard $(NATIVE_DIR)/plugin/*.cpp))
PRODUCTION_PLUGIN_SOURCES := $(filter-out %/probe_processor.cpp %/benchmark_recorder.cpp,$(PLUGIN_SOURCES))
PROBE_PLUGIN_SOURCES := $(filter-out %/benchmark_recorder.cpp,$(PLUGIN_SOURCES))

TEST_BINARY := $(BUILD_DIR)/bin/native_tests
SANITIZE_BINARY := $(BUILD_DIR)/bin/native_tests_sanitize
TSAN_BINARY := $(BUILD_DIR)/bin/native_tests_tsan
PROBE_ARTIFACT := $(BUILD_DIR)/clap/M3_Polyphonic_Audio_to_MIDI_Probe.clap
PRODUCTION_ARTIFACT := $(BUILD_DIR)/clap/M3_Polyphonic_Audio_to_MIDI.clap
BENCHMARK_BINARY := $(BUILD_DIR)/bin/native_benchmark

.PHONY: all test sanitize tsan probe production benchmark clean

all: test

test:
	@mkdir -p $(dir $(TEST_BINARY))
	$(CXX) $(COMMON_CPPFLAGS) $(TEST_CXXFLAGS) $(CORE_SOURCES) $(PLUGIN_SOURCES) $(TEST_SOURCES) -pthread -lm -o $(TEST_BINARY)
	$(TEST_BINARY)

sanitize:
	@mkdir -p $(dir $(SANITIZE_BINARY))
	$(CXX) $(COMMON_CPPFLAGS) $(SANITIZE_CXXFLAGS) $(CORE_SOURCES) $(PLUGIN_SOURCES) $(TEST_SOURCES) -pthread -lm -o $(SANITIZE_BINARY)
	$(SANITIZE_BINARY)

tsan:
	@mkdir -p $(dir $(TSAN_BINARY))
	$(CXX) $(COMMON_CPPFLAGS) $(TSAN_CXXFLAGS) $(CORE_SOURCES) $(PLUGIN_SOURCES) $(TEST_SOURCES) -pthread -lm -o $(TSAN_BINARY)
	$(TSAN_BINARY)

probe:
	@test -f $(NATIVE_DIR)/plugin/clap_entry.cpp
	@mkdir -p $(dir $(PROBE_ARTIFACT))
	$(CXX) $(COMMON_CPPFLAGS) $(PROBE_CXXFLAGS) $(CORE_SOURCES) $(PROBE_PLUGIN_SOURCES) $(SHARED_LDFLAGS) -lm -o $(PROBE_ARTIFACT)

production:
	@test -f $(NATIVE_DIR)/plugin/clap_entry.cpp
	@mkdir -p $(dir $(PRODUCTION_ARTIFACT))
	$(CXX) $(COMMON_CPPFLAGS) $(PRODUCTION_CXXFLAGS) $(CORE_SOURCES) $(PRODUCTION_PLUGIN_SOURCES) $(SHARED_LDFLAGS) -lm -o $(PRODUCTION_ARTIFACT)

benchmark:
	@test -f $(NATIVE_DIR)/bench/benchmark_main.cpp
	@mkdir -p $(dir $(BENCHMARK_BINARY))
	$(CXX) $(COMMON_CPPFLAGS) $(COMMON_CXXFLAGS) -O3 -DNDEBUG -DM3_BENCHMARKING $(CORE_SOURCES) $(NATIVE_DIR)/bench/benchmark_main.cpp -lm -o $(BENCHMARK_BINARY)

clean:
	$(RM) -r $(BUILD_DIR)/bin $(BUILD_DIR)/obj $(BUILD_DIR)/clap
