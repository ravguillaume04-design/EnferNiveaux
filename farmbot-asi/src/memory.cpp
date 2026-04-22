#include "memory.h"
#include <Windows.h>
#include <cstring>

namespace Memory {

    uintptr_t PatternScanRange(uintptr_t start, size_t size, const char* pattern, const char* mask) {
        size_t patLen = strlen(mask);
        for (size_t i = 0; i < size - patLen; ++i) {
            bool found = true;
            for (size_t j = 0; j < patLen; ++j) {
                if (mask[j] != '?' && ((const char*)(start + i))[j] != pattern[j]) {
                    found = false;
                    break;
                }
            }
            if (found) return start + i;
        }
        return 0;
    }

    uintptr_t PatternScan(const char* moduleName, const char* pattern, const char* mask) {
        HMODULE hMod = GetModuleHandleA(moduleName);
        if (!hMod) return 0;

        auto* dos = (IMAGE_DOS_HEADER*)hMod;
        auto* nt  = (IMAGE_NT_HEADERS*)((uintptr_t)hMod + dos->e_lfanew);
        uintptr_t base = (uintptr_t)hMod;
        size_t    size = nt->OptionalHeader.SizeOfImage;

        return PatternScanRange(base, size, pattern, mask);
    }

} // namespace Memory
