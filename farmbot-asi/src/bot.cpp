#include "bot.h"
#include "natives.h"
#include <Windows.h>
#include <cmath>
#include <chrono>

namespace Bot {

std::vector<Waypoint> g_waypoints;
std::atomic<bool>     g_running{false};
int                   g_intervalSec = 0;
int                   g_currentWp   = -1;

// ------------------------------------------------------------------ //
//  Internal state                                                      //
// ------------------------------------------------------------------ //

static bool  s_navigating   = false;
static float s_targetX = 0, s_targetY = 0, s_targetZ = 0;
static std::chrono::steady_clock::time_point s_arrivedAt;
static bool  s_waitingAction = false;
static bool  s_waitingLoop   = false;
static std::chrono::steady_clock::time_point s_loopWaitStart;

// ------------------------------------------------------------------ //
//  Helpers                                                            //
// ------------------------------------------------------------------ //

static void PressKey(WORD vk, DWORD holdMs = 80) {
    INPUT in[2]{};
    in[0].type       = INPUT_KEYBOARD;
    in[0].ki.wVk     = vk;
    in[1].type       = INPUT_KEYBOARD;
    in[1].ki.wVk     = vk;
    in[1].ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(1, &in[0], sizeof(INPUT));
    Sleep(holdMs);
    SendInput(1, &in[1], sizeof(INPUT));
}

static float Distance2D(float ax, float ay, float bx, float by) {
    float dx = ax - bx, dy = ay - by;
    return sqrtf(dx*dx + dy*dy);
}

// ------------------------------------------------------------------ //
//  Public API                                                          //
// ------------------------------------------------------------------ //

void AddWaypointHere(const std::string& action, const std::string& label) {
    int ped = Natives::PlayerPedId();
    float x, y, z;
    Natives::GetEntityCoords(ped, &x, &y, &z);
    g_waypoints.push_back({x, y, z, action, label.empty() ? ("WP" + std::to_string(g_waypoints.size() + 1)) : label});
}

void RemoveWaypoint(int idx) {
    if (idx >= 0 && idx < (int)g_waypoints.size())
        g_waypoints.erase(g_waypoints.begin() + idx);
}

void Start() {
    if (g_waypoints.empty()) return;
    g_running     = true;
    g_currentWp   = 0;
    s_navigating  = false;
    s_waitingAction = false;
    s_waitingLoop   = false;
}

void Stop() {
    g_running    = false;
    g_currentWp  = -1;
    s_navigating = false;
    int ped = Natives::PlayerPedId();
    if (ped) Natives::ClearPedTasks(ped);
}

// ------------------------------------------------------------------ //
//  Tick — called every frame from Menu::Draw on the game thread       //
// ------------------------------------------------------------------ //

void Tick() {
    if (!g_running || g_waypoints.empty()) return;
    if (g_currentWp < 0 || g_currentWp >= (int)g_waypoints.size()) {
        g_currentWp = 0;
    }

    auto now = std::chrono::steady_clock::now();

    // ---- Loop interval wait ----------------------------------------
    if (s_waitingLoop) {
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - s_loopWaitStart).count();
        if (elapsed >= g_intervalSec) {
            s_waitingLoop = false;
            g_currentWp   = 0;
        }
        return;
    }

    // ---- Waiting for action delay ----------------------------------
    if (s_waitingAction) {
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - s_arrivedAt).count();
        if (elapsed < 1500) return;   // hold 1.5s at waypoint

        const auto& wp = g_waypoints[g_currentWp];
        const std::string& act = wp.action;

        if (act == "e") {
            PressKey('E', 100);
        } else if (act == "g") {
            PressKey('G', 100);
        } else if (act == "k") {
            PressKey('K', 100);
        }
        // Extra delay after action
        Sleep(500);

        s_waitingAction = false;
        g_currentWp++;

        if (g_currentWp >= (int)g_waypoints.size()) {
            // Loop complete
            if (g_intervalSec > 0) {
                s_waitingLoop    = true;
                s_loopWaitStart  = std::chrono::steady_clock::now();
            } else {
                g_currentWp = 0;
            }
        }
        return;
    }

    // ---- Navigate to current waypoint ------------------------------
    const auto& wp = g_waypoints[g_currentWp];
    int ped = Natives::PlayerPedId();
    if (!ped) return;

    float px, py, pz;
    Natives::GetEntityCoords(ped, &px, &py, &pz);

    float dist = Distance2D(px, py, wp.x, wp.y);

    if (!s_navigating) {
        // Issue TASK_GO_TO_COORD_ANY_MEANS
        Natives::TaskGoToCoordAnyMeans(ped, wp.x, wp.y, wp.z, 2.0f, 0);
        s_targetX    = wp.x;
        s_targetY    = wp.y;
        s_targetZ    = wp.z;
        s_navigating = true;
    }

    // Check arrival (within 2m)
    if (dist < 2.0f) {
        Natives::ClearPedTasks(ped);
        s_navigating = false;

        if (!wp.action.empty()) {
            s_arrivedAt     = std::chrono::steady_clock::now();
            s_waitingAction = true;
        } else {
            g_currentWp++;
            if (g_currentWp >= (int)g_waypoints.size()) {
                if (g_intervalSec > 0) {
                    s_waitingLoop   = true;
                    s_loopWaitStart = std::chrono::steady_clock::now();
                } else {
                    g_currentWp = 0;
                }
            }
        }
    }
}

} // namespace Bot
