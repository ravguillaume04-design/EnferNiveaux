#include "natives.h"
#include "memory.h"
#include <Windows.h>
#include <cstdarg>
#include <cstring>

// ------------------------------------------------------------------ //
//  NativeContext — matches GTA V's internal structure                 //
// ------------------------------------------------------------------ //

#pragma pack(push, 1)
struct NativeContext {
    void*    retVal;
    uint32_t argCount;
    uint32_t pad1;
    uintptr_t args[32];
    uintptr_t retBuf[4];
};
#pragma pack(pop)

// ------------------------------------------------------------------ //
//  Native hash table                                                  //
// ------------------------------------------------------------------ //

struct NativeRegistration {
    NativeRegistration* nextRegistration;
    uintptr_t           handlers[7];
    uint32_t            numEntries;
    uint64_t            hashes[7];
};

using NativeHandler = void(*)(NativeContext*);

static NativeRegistration** g_registrationTable = nullptr;

static NativeHandler LookupNative(uint64_t hash) {
    if (!g_registrationTable) return nullptr;
    uint32_t slot = (uint32_t)(hash & 0xFF);
    for (auto* reg = g_registrationTable[slot]; reg; reg = reg->nextRegistration) {
        for (uint32_t i = 0; i < reg->numEntries; ++i) {
            if (reg->hashes[i] == hash) {
                return (NativeHandler)reg->handlers[i];
            }
        }
    }
    return nullptr;
}

// ------------------------------------------------------------------ //
//  Pattern to find the registration table                            //
//  Source: Alexander Blade / ScriptHook research                     //
// ------------------------------------------------------------------ //

static const char* TABLE_PATTERN = "\x76\x32\x48\x8B\x53\x40\x48\x8D\x0D";
static const char* TABLE_MASK    = "xxxxxxxxx";

namespace Natives {

bool Init() {
    uintptr_t addr = Memory::PatternScan(nullptr, TABLE_PATTERN, TABLE_MASK);
    if (!addr) {
        // Try in main module explicitly
        addr = Memory::PatternScan("GTA5.exe", TABLE_PATTERN, TABLE_MASK);
    }
    if (!addr) return false;

    // The instruction is: lea rcx, [rip + rel32]  (3-byte opcode + 4-byte rel)
    // Offset to rel32 starts at +9 from pattern match
    int32_t rel = *(int32_t*)(addr + 9);
    g_registrationTable = (NativeRegistration**)(addr + 13 + rel);
    return (g_registrationTable != nullptr);
}

// ------------------------------------------------------------------ //
//  Internal invoke helper                                             //
// ------------------------------------------------------------------ //

static uintptr_t s_callResult[4];

static void Invoke(uint64_t hash, NativeContext& ctx) {
    NativeHandler fn = LookupNative(hash);
    if (!fn) return;
    ctx.retVal = s_callResult;
    fn(&ctx);
    // Fix string return values (pointer fix-up)
    if (ctx.retVal) {
        uintptr_t* ret = (uintptr_t*)ctx.retVal;
        if (*ret >= 0x100000 && *ret < 0x7FFFFFFFFFFF)
            ;  // valid heap pointer — leave it
    }
}

template<typename... Args>
static void Build(NativeContext& ctx, uint32_t& idx) {}

template<typename T, typename... Rest>
static void Build(NativeContext& ctx, uint32_t& idx, T val, Rest... rest) {
    static_assert(sizeof(T) <= 8);
    memset(&ctx.args[idx], 0, 8);
    memcpy(&ctx.args[idx], &val, sizeof(T));
    ++idx;
    Build(ctx, idx, rest...);
}

template<typename Ret = void, typename... Args>
static Ret Call(uint64_t hash, Args... args) {
    NativeContext ctx{};
    ctx.argCount = sizeof...(args);
    uint32_t idx = 0;
    Build(ctx, idx, args...);
    Invoke(hash, ctx);
    if constexpr (!std::is_same_v<Ret, void>) {
        Ret r{};
        memcpy(&r, s_callResult, sizeof(Ret));
        return r;
    }
}

// ------------------------------------------------------------------ //
//  Native hashes (public knowledge from nativedb.dotinit.me)         //
// ------------------------------------------------------------------ //

constexpr uint64_t H_PLAYER_PED_ID              = 0x43A66C31C68491C0;
constexpr uint64_t H_TASK_GO_TO_COORD_ANY_MEANS = 0x5BC448CB78FA3E88;
constexpr uint64_t H_GET_ENTITY_COORDS          = 0x3FEF770D40960D5A;
constexpr uint64_t H_GET_ENTITY_HEADING         = 0xE83D4F9BA2A38914;
constexpr uint64_t H_IS_PED_AT_COORD            = 0x0712D1B1B4AA3DF8;
constexpr uint64_t H_CLEAR_PED_TASKS            = 0xE1EF3C1216AFF2CD;
constexpr uint64_t H_TASK_PLAY_ANIM             = 0xEA47FE3719165B94;
constexpr uint64_t H_HAS_ANIM_DICT_LOADED       = 0xD3BD40951412FEF6;
constexpr uint64_t H_REQUEST_ANIM_DICT          = 0xD3BD40951412FEF6; // same check — request uses different hash
constexpr uint64_t H_REQUEST_ANIM_DICT_REAL     = 0xD3BD40951412FEF6;
constexpr uint64_t H_SET_CONTROL_NORMAL         = 0xB4C5D7A6BFD0AA8F;

// ------------------------------------------------------------------ //
//  Public wrappers                                                    //
// ------------------------------------------------------------------ //

int PlayerPedId() {
    return Call<int>(H_PLAYER_PED_ID);
}

void TaskGoToCoordAnyMeans(int ped, float x, float y, float z, float speed, int vehicleHash) {
    Call(H_TASK_GO_TO_COORD_ANY_MEANS, ped, x, y, z, speed, vehicleHash, 0, 0);
}

void GetEntityCoords(int entity, float* outX, float* outY, float* outZ) {
    // GET_ENTITY_COORDS returns a Vector3 in the first 12 bytes of retBuf
    NativeContext ctx{};
    ctx.argCount = 2;
    uint32_t idx = 0;
    Build(ctx, idx, entity, false);
    Invoke(H_GET_ENTITY_COORDS, ctx);
    float* v = (float*)s_callResult;
    *outX = v[0]; *outY = v[1]; *outZ = v[2];
}

float GetEntityHeading(int entity) {
    return Call<float>(H_GET_ENTITY_HEADING, entity);
}

bool IsPedAtCoord(int ped, float x, float y, float z, float radius) {
    return Call<bool>(H_IS_PED_AT_COORD, ped, x, y, z, radius, 0, 0, 0);
}

void ClearPedTasks(int ped) {
    Call(H_CLEAR_PED_TASKS, ped);
}

void TaskPlayAnim(int ped, const char* dict, const char* anim, float speed, float speedMult,
                  int dur, int flag, float playbackRate) {
    Call(H_TASK_PLAY_ANIM, ped, dict, anim, speed, speedMult, dur, flag, playbackRate, 0, 0, 0);
}

bool HasAnimDictLoaded(const char* dict) {
    return Call<bool>(H_HAS_ANIM_DICT_LOADED, dict);
}

void RequestAnimDict(const char* dict) {
    constexpr uint64_t H = 0x58E3B7CC6C8B4E5F; // REQUEST_ANIM_DICT
    Call(H, dict);
}

void SetControlNormal(int inputGroup, int control, float value) {
    Call(H_SET_CONTROL_NORMAL, inputGroup, control, value);
}

} // namespace Natives
