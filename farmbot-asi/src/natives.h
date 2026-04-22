#pragma once
#include <cstdint>
#include <cstddef>

// ------------------------------------------------------------------ //
//  Native calling infrastructure for GTA V / FiveM                   //
// ------------------------------------------------------------------ //

namespace Natives {

bool Init();

// Low-level call — use the typed wrappers below
void CallNative(uint64_t hash, ...);

// ------------------------------------------------------------------ //
//  Typed native wrappers                                              //
// ------------------------------------------------------------------ //

// Returns the local player ped
int    PlayerPedId();

// Move ped to (x,y,z) using pathfinding (any means)
void   TaskGoToCoordAnyMeans(int ped, float x, float y, float z, float speed, int vehicleHash);

// Returns entity world coordinates
void   GetEntityCoords(int entity, float* outX, float* outY, float* outZ);

// Returns entity heading in degrees
float  GetEntityHeading(int entity);

// Returns true when ped is within radius of coord
bool   IsPedAtCoord(int ped, float x, float y, float z, float radius);

// Clear all tasks (abort navigation)
void   ClearPedTasks(int ped);

// Play animation
void   TaskPlayAnim(int ped, const char* dict, const char* anim, float speed, float speedMult,
                    int dur, int flag, float playbackRate);

// Check anim dict loaded
bool   HasAnimDictLoaded(const char* dict);

// Request anim dict
void   RequestAnimDict(const char* dict);

// Press a key via native (for actions)
void   SetControlNormal(int inputGroup, int control, float value);

} // namespace Natives
