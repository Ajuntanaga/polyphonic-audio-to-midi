NATIVE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT := $(abspath $(NATIVE_DIR)/..)
BUILD_DIR ?= $(ROOT)/build/vst3
PYTHON ?= python3
GUARD := $(PYTHON) $(ROOT)/tools/run_guarded_native_build.py

.PHONY: all test sanitize tsan probe production benchmark clean

all: test

test:
	$(GUARD) --timeout 180 -- cmake -S $(ROOT) -B $(BUILD_DIR)/debug -DCMAKE_BUILD_TYPE=Debug
	$(GUARD) --timeout 300 -- cmake --build $(BUILD_DIR)/debug --target m3_native_tests -j1
	$(GUARD) --timeout 180 -- ctest --test-dir $(BUILD_DIR)/debug --output-on-failure -j1

sanitize:
	$(GUARD) --timeout 180 -- cmake -S $(ROOT) -B $(BUILD_DIR)/sanitize -DCMAKE_BUILD_TYPE=Debug -DM3_ENABLE_ASAN_UBSAN=ON
	$(GUARD) --timeout 300 -- cmake --build $(BUILD_DIR)/sanitize --target m3_native_tests -j1
	$(GUARD) --timeout 180 -- ctest --test-dir $(BUILD_DIR)/sanitize --output-on-failure -j1

tsan:
	$(GUARD) --timeout 180 -- cmake -S $(ROOT) -B $(BUILD_DIR)/tsan -DCMAKE_BUILD_TYPE=Debug -DM3_ENABLE_TSAN=ON
	$(GUARD) --timeout 300 -- cmake --build $(BUILD_DIR)/tsan --target m3_native_tests -j1
	$(GUARD) --timeout 180 -- ctest --test-dir $(BUILD_DIR)/tsan --output-on-failure -j1

probe:
	$(GUARD) --timeout 180 -- cmake -S $(ROOT) -B $(BUILD_DIR)/release -DCMAKE_BUILD_TYPE=Release
	$(GUARD) --timeout 300 -- cmake --build $(BUILD_DIR)/release --target m3_vst3_probe -j1

production:
	$(GUARD) --timeout 180 -- cmake -S $(ROOT) -B $(BUILD_DIR)/release -DCMAKE_BUILD_TYPE=Release
	$(GUARD) --timeout 300 -- cmake --build $(BUILD_DIR)/release --target m3_vst3_production -j1

benchmark:
	$(GUARD) --timeout 180 -- cmake -S $(ROOT) -B $(BUILD_DIR)/benchmark -DCMAKE_BUILD_TYPE=Release
	$(GUARD) --timeout 300 -- cmake --build $(BUILD_DIR)/benchmark --target m3_vst3_benchmark -j1

clean:
	cmake -E remove_directory $(BUILD_DIR)
