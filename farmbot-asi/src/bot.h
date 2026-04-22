#pragma once
#include <vector>
#include <string>
#include <atomic>

struct Waypoint {
    float x, y, z;
    std::string action; // "" | "e" | "g" | "k"
    std::string label;
};

namespace Bot {
    extern std::vector<Waypoint> g_waypoints;
    extern std::atomic<bool>     g_running;
    extern int                   g_intervalSec;  // pause between loops (seconds)
    extern int                   g_currentWp;    // index currently targeted

    void AddWaypointHere(const std::string& action = "", const std::string& label = "");
    void RemoveWaypoint(int idx);
    void Start();
    void Stop();
    void Tick();   // called every frame from menu (main game thread)
}
