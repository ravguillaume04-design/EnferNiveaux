#include "menu.h"
#include "bot.h"
#include "natives.h"
#include <imgui.h>
#include <Windows.h>
#include <string>
#include <array>

namespace Menu {

bool g_visible = false;

// ------------------------------------------------------------------ //
//  Toggle key — Numpad + (VK_ADD = 0x6B)                              //
// ------------------------------------------------------------------ //

static bool s_prevPlus = false;

static void CheckToggleKey() {
    bool cur = (GetAsyncKeyState(VK_ADD) & 0x8000) != 0;
    if (cur && !s_prevPlus) g_visible = !g_visible;
    s_prevPlus = cur;
}

// ------------------------------------------------------------------ //
//  Action combo                                                        //
// ------------------------------------------------------------------ //

static const char* k_actions[]     = { "Aucune", "E (action)", "G (verrou)", "K (inventaire)" };
static const char* k_actionKeys[]  = { "",        "e",          "g",           "k" };
static int         s_actionIdx     = 0;
static char        s_wpLabel[64]   = "";

// ------------------------------------------------------------------ //
//  Draw                                                                //
// ------------------------------------------------------------------ //

void Draw() {
    CheckToggleKey();
    Bot::Tick();

    if (!g_visible) return;

    ImGui::SetNextWindowSize(ImVec2(340, 460), ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowPos(ImVec2(20, 20), ImGuiCond_FirstUseEver);

    ImGui::Begin("FarmBot ASI", &g_visible,
        ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoResize);

    // ---- Status -----------------------------------------------------
    {
        float px = 0, py = 0, pz = 0;
        int ped = Natives::PlayerPedId();
        if (ped) Natives::GetEntityCoords(ped, &px, &py, &pz);

        ImGui::TextDisabled("Position : %.1f / %.1f / %.1f", px, py, pz);

        if (Bot::g_running) {
            ImGui::TextColored({0.2f,1.0f,0.2f,1.0f}, "BOT ACTIF  [WP %d/%d]",
                Bot::g_currentWp + 1, (int)Bot::g_waypoints.size());
        } else {
            ImGui::TextColored({0.7f,0.7f,0.7f,1.0f}, "Bot inactif");
        }
    }

    ImGui::Separator();

    // ---- Interval ---------------------------------------------------
    ImGui::Text("Intervalle entre les cycles :");
    static int s_min = 0, s_sec = 0;
    ImGui::SetNextItemWidth(60);
    ImGui::InputInt("min##iv", &s_min, 1, 5);
    ImGui::SameLine();
    ImGui::SetNextItemWidth(60);
    ImGui::InputInt("sec##iv", &s_sec, 1, 15);
    if (s_min < 0) s_min = 0;
    if (s_sec < 0) s_sec = 0;
    if (s_sec > 59) s_sec = 59;
    Bot::g_intervalSec = s_min * 60 + s_sec;

    ImGui::Separator();

    // ---- Start / Stop -----------------------------------------------
    if (!Bot::g_running) {
        if (ImGui::Button("  Demarrer  ", ImVec2(-1, 32))) Bot::Start();
    } else {
        if (ImGui::Button("  Arreter   ", ImVec2(-1, 32))) Bot::Stop();
    }

    ImGui::Separator();

    // ---- Add waypoint -----------------------------------------------
    ImGui::Text("Ajouter un waypoint ici :");
    ImGui::SetNextItemWidth(140);
    ImGui::InputText("Nom##lbl", s_wpLabel, sizeof(s_wpLabel));
    ImGui::SetNextItemWidth(160);
    ImGui::Combo("Action##act", &s_actionIdx, k_actions, 4);
    if (ImGui::Button("+ Ajouter waypoint", ImVec2(-1, 0))) {
        Bot::AddWaypointHere(k_actionKeys[s_actionIdx], s_wpLabel);
        s_wpLabel[0] = '\0';
        s_actionIdx  = 0;
    }

    ImGui::Separator();

    // ---- Waypoint list ----------------------------------------------
    ImGui::Text("Waypoints (%d) :", (int)Bot::g_waypoints.size());
    ImGui::BeginChild("wplist", ImVec2(0, 160), true);
    for (int i = 0; i < (int)Bot::g_waypoints.size(); ++i) {
        const auto& wp = Bot::g_waypoints[i];
        bool isCurrent = Bot::g_running && (Bot::g_currentWp == i);

        ImGui::PushID(i);
        if (isCurrent) ImGui::PushStyleColor(ImGuiCol_Text, {0.3f,1.0f,0.3f,1.0f});

        char buf[128];
        snprintf(buf, sizeof(buf), "[%d] %s  (%.0f, %.0f, %.0f)  %s",
            i+1,
            wp.label.c_str(),
            wp.x, wp.y, wp.z,
            wp.action.empty() ? "" : ("[" + wp.action + "]").c_str());
        ImGui::TextUnformatted(buf);

        if (isCurrent) ImGui::PopStyleColor();

        ImGui::SameLine();
        if (ImGui::SmallButton("X")) {
            Bot::RemoveWaypoint(i);
            ImGui::PopID();
            break;
        }
        if (ImGui::IsItemHovered()) ImGui::SetTooltip("Supprimer ce waypoint");
        ImGui::PopID();
    }
    ImGui::EndChild();

    if (ImGui::Button("Tout effacer", ImVec2(-1, 0))) {
        Bot::Stop();
        Bot::g_waypoints.clear();
    }

    ImGui::Separator();
    ImGui::TextDisabled("Numpad + : afficher/masquer");

    ImGui::End();
}

} // namespace Menu
