set(M3_VST3_SDK_ROOT "${M3_PROJECT_ROOT}/third_party/vst3sdk")

function(m3_add_pinned_vst3_sdk)
    set(required_sdk_paths
        CMakeLists.txt
        LICENSE.txt
        base/source/fobject.cpp
        cmake/modules/SMTG_VST3_SDK.cmake
        pluginterfaces/base/funknown.h
        public.sdk/source/vst/vstaudioeffect.h
        public.sdk/samples/vst-hosting/validator/CMakeLists.txt
        public.sdk/samples/vst-utilities/moduleinfotool/CMakeLists.txt
    )
    foreach(relative_path IN LISTS required_sdk_paths)
        if(NOT EXISTS "${M3_VST3_SDK_ROOT}/${relative_path}")
            message(FATAL_ERROR "Pinned VST3 SDK path is absent: ${relative_path}")
        endif()
    endforeach()

    add_subdirectory(
        "${M3_VST3_SDK_ROOT}"
        "${CMAKE_BINARY_DIR}/sdk"
        EXCLUDE_FROM_ALL
    )

    # The SDK hosting tree supplies validator even with unrelated host samples
    # disabled. Utilities stay disabled globally; add only moduleinfotool as a
    # separately excluded target for later explicit validation targets.
    set(SDK_ROOT "${M3_VST3_SDK_ROOT}")
    if(NOT TARGET validator)
        add_subdirectory(
            "${M3_VST3_SDK_ROOT}/public.sdk/samples/vst-hosting/validator"
            "${CMAKE_BINARY_DIR}/sdk/validator"
            EXCLUDE_FROM_ALL
        )
    endif()
    if(NOT TARGET moduleinfotool)
        add_subdirectory(
            "${M3_VST3_SDK_ROOT}/public.sdk/samples/vst-utilities/moduleinfotool"
            "${CMAKE_BINARY_DIR}/sdk/moduleinfotool"
            EXCLUDE_FROM_ALL
        )
    endif()
endfunction()
