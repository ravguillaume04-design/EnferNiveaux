#pragma once
#include <cstdint>
#include <cstddef>

namespace Memory {
    uintptr_t PatternScan(const char* module, const char* pattern, const char* mask);
    uintptr_t PatternScanRange(uintptr_t start, size_t size, const char* pattern, const char* mask);
}
