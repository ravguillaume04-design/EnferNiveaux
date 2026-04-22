#include <Windows.h>
#include "natives.h"
#include "hooks.h"
#include "menu.h"

// ------------------------------------------------------------------ //
//  Main thread — waits for GTA V to fully load, then initialises      //
// ------------------------------------------------------------------ //

static DWORD WINAPI MainThread(LPVOID) {
    // Wait 8 seconds for FiveM/GTA V engine to be fully ready
    Sleep(8000);

    // Init native table pointer
    if (!Natives::Init()) {
        MessageBoxA(nullptr,
            "FarmBot ASI: impossible de localiser la table des natives.\n"
            "Verifie que FiveM est bien en jeu (pas dans le menu principal).",
            "FarmBot ASI", MB_ICONERROR);
        return 1;
    }

    // Hook DX11 Present → ImGui overlay
    if (!Hooks::Init()) {
        MessageBoxA(nullptr,
            "FarmBot ASI: echec du hook DirectX 11.\n"
            "Verifie que le jeu utilise le mode fenetres sans bordures.",
            "FarmBot ASI", MB_ICONERROR);
        return 1;
    }

    // Show menu on startup
    Menu::g_visible = true;

    return 0;
}

// ------------------------------------------------------------------ //
//  DLL entry point                                                     //
// ------------------------------------------------------------------ //

BOOL WINAPI DllMain(HINSTANCE hInst, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hInst);
        CreateThread(nullptr, 0, MainThread, nullptr, 0, nullptr);
    } else if (reason == DLL_PROCESS_DETACH) {
        Hooks::Shutdown();
    }
    return TRUE;
}
