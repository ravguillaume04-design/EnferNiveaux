cmake_minimum_required(VERSION 3.20)
project(FarmBotASI CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ------------------------------------------------------------------ #
#  Output as .asi (renamed DLL)                                        #
# ------------------------------------------------------------------ #
add_library(FarmBot SHARED
    src/dllmain.cpp
    src/memory.cpp
    src/natives.cpp
    src/hooks.cpp
    src/menu.cpp
    src/bot.cpp

    # ImGui sources (vendored)
    vendor/imgui/imgui.cpp
    vendor/imgui/imgui_draw.cpp
    vendor/imgui/imgui_tables.cpp
    vendor/imgui/imgui_widgets.cpp
    vendor/imgui/backends/imgui_impl_dx11.cpp
    vendor/imgui/backends/imgui_impl_win32.cpp
)

# Rename output to .asi
set_target_properties(FarmBot PROPERTIES
    OUTPUT_NAME  "FarmBot"
    SUFFIX       ".asi"
    PREFIX       ""
)

# ------------------------------------------------------------------ #
#  Include dirs                                                         #
# ------------------------------------------------------------------ #
target_include_directories(FarmBot PRIVATE
    src
    vendor/imgui
    vendor/imgui/backends
    vendor/minhook/include
)

# ------------------------------------------------------------------ #
#  MinHook — built from source                                          #
# ------------------------------------------------------------------ #
add_library(minhook STATIC
    vendor/minhook/src/buffer.c
    vendor/minhook/src/hook.c
    vendor/minhook/src/trampoline.c
    vendor/minhook/src/hde/hde64.c
)
target_include_directories(minhook PUBLIC vendor/minhook/include)

target_link_libraries(FarmBot PRIVATE
    minhook
    d3d11
    dxgi
)

# ------------------------------------------------------------------ #
#  Windows subsystem                                                    #
# ------------------------------------------------------------------ #
target_compile_definitions(FarmBot PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    _CRT_SECURE_NO_WARNINGS
)
