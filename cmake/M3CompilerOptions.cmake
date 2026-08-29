function(m3_apply_project_options target)
    if(NOT TARGET "${target}")
        message(FATAL_ERROR "unknown project target: ${target}")
    endif()

    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options("${target}" PRIVATE
            -Wall
            -Wextra
            -Wpedantic
            -Wconversion
            -Wshadow
            -Werror
            -fno-exceptions
            -fno-rtti
            -fstack-protector-strong
            -fvisibility=hidden
            "-ffile-prefix-map=${M3_PROJECT_ROOT}=."
            "-fmacro-prefix-map=${M3_PROJECT_ROOT}=."
        )
        target_link_options("${target}" PRIVATE
            -Wl,-z,relro
            -Wl,-z,now
            -Wl,--no-undefined
            -Wl,--build-id=none
        )

        if(M3_ENABLE_ASAN_UBSAN)
            target_compile_options("${target}" PRIVATE
                -fsanitize=address,undefined
                -fno-omit-frame-pointer
            )
            target_link_options("${target}" PRIVATE -fsanitize=address,undefined)
        elseif(M3_ENABLE_TSAN)
            target_compile_options("${target}" PRIVATE
                -fsanitize=thread
                -fno-omit-frame-pointer
            )
            target_link_options("${target}" PRIVATE -fsanitize=thread)
        endif()
    else()
        message(FATAL_ERROR "The native hardening contract requires GNU or Clang")
    endif()
endfunction()
