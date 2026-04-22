#include "hooks.h"
#include "menu.h"
#include <Windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <imgui.h>
#include <imgui_impl_dx11.h>
#include <imgui_impl_win32.h>
#include <MinHook.h>

#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")

// ------------------------------------------------------------------ //
//  Types                                                              //
// ------------------------------------------------------------------ //

using PresentFn  = HRESULT(WINAPI*)(IDXGISwapChain*, UINT, UINT);
using WndProcFn  = LRESULT(WINAPI*)(HWND, UINT, WPARAM, LPARAM);

static PresentFn  oPresent  = nullptr;
static WndProcFn  oWndProc  = nullptr;

static ID3D11Device*           g_device  = nullptr;
static ID3D11DeviceContext*    g_context = nullptr;
static ID3D11RenderTargetView* g_rtv     = nullptr;
static HWND                    g_hwnd    = nullptr;
static bool                    g_ready   = false;

// ------------------------------------------------------------------ //
//  WndProc hook — forwards input to ImGui without blocking the game   //
// ------------------------------------------------------------------ //

extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND, UINT, WPARAM, LPARAM);

static LRESULT WINAPI HookedWndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    ImGui_ImplWin32_WndProcHandler(hWnd, msg, wParam, lParam);
    // Always pass through to the game — we never consume events
    return CallWindowProcW(oWndProc, hWnd, msg, wParam, lParam);
}

// ------------------------------------------------------------------ //
//  Present hook                                                        //
// ------------------------------------------------------------------ //

static HRESULT WINAPI HookedPresent(IDXGISwapChain* chain, UINT syncInterval, UINT flags) {
    if (!g_ready) {
        // One-time init on first Present call
        chain->GetDevice(__uuidof(ID3D11Device), (void**)&g_device);
        g_device->GetImmediateContext(&g_context);

        DXGI_SWAP_CHAIN_DESC desc{};
        chain->GetDesc(&desc);
        g_hwnd = desc.OutputWindow;

        ID3D11Texture2D* back = nullptr;
        chain->GetBuffer(0, __uuidof(ID3D11Texture2D), (void**)&back);
        g_device->CreateRenderTargetView(back, nullptr, &g_rtv);
        back->Release();

        // Hook WndProc after we have the HWND
        oWndProc = (WndProcFn)SetWindowLongPtrW(
            g_hwnd, GWLP_WNDPROC, (LONG_PTR)HookedWndProc);

        // ImGui
        ImGui::CreateContext();
        ImGuiIO& io = ImGui::GetIO();
        io.ConfigFlags |= ImGuiConfigFlags_NoMouseCursorChange;
        ImGui_ImplWin32_Init(g_hwnd);
        ImGui_ImplDX11_Init(g_device, g_context);

        // Style
        ImGui::StyleColorsDark();
        ImGuiStyle& style = ImGui::GetStyle();
        style.WindowRounding = 6.0f;
        style.FrameRounding  = 4.0f;

        g_ready = true;
    }

    // Resize RTV if swap chain was resized
    // (Simple approach: recreate if back buffer size changed)
    {
        ID3D11Texture2D* back = nullptr;
        if (SUCCEEDED(chain->GetBuffer(0, __uuidof(ID3D11Texture2D), (void**)&back))) {
            D3D11_TEXTURE2D_DESC desc{};
            back->GetDesc(&desc);
            D3D11_RENDER_TARGET_VIEW_DESC rtvDesc{};
            if (g_rtv) g_rtv->GetDesc(&rtvDesc); // just check it exists
            back->Release();
        }
    }

    ImGui_ImplDX11_NewFrame();
    ImGui_ImplWin32_NewFrame();
    ImGui::NewFrame();

    Menu::Draw();

    ImGui::Render();
    g_context->OMSetRenderTargets(1, &g_rtv, nullptr);
    ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());

    return oPresent(chain, syncInterval, flags);
}

// ------------------------------------------------------------------ //
//  Init — create dummy device to get vtable, then hook index 8        //
// ------------------------------------------------------------------ //

namespace Hooks {

bool Init() {
    // Create a temporary swap chain just to read the vtable
    DXGI_SWAP_CHAIN_DESC sd{};
    sd.BufferCount       = 1;
    sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.BufferUsage       = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.OutputWindow      = GetForegroundWindow();
    sd.SampleDesc.Count  = 1;
    sd.Windowed          = TRUE;
    sd.SwapEffect        = DXGI_SWAP_EFFECT_DISCARD;

    ID3D11Device*        tmpDev   = nullptr;
    IDXGISwapChain*      tmpChain = nullptr;
    ID3D11DeviceContext* tmpCtx   = nullptr;
    D3D_FEATURE_LEVEL    feat;

    HRESULT hr = D3D11CreateDeviceAndSwapChain(
        nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0,
        nullptr, 0, D3D11_SDK_VERSION,
        &sd, &tmpChain, &tmpDev, &feat, &tmpCtx);

    if (FAILED(hr)) return false;

    void** vtable = *(void***)tmpChain;  // IDXGISwapChain vtable
    void*  presentAddr = vtable[8];      // Present is at index 8

    tmpChain->Release();
    tmpDev->Release();
    tmpCtx->Release();

    // MinHook
    MH_Initialize();
    if (MH_CreateHook(presentAddr, &HookedPresent, (void**)&oPresent) != MH_OK)
        return false;
    if (MH_EnableHook(presentAddr) != MH_OK)
        return false;

    return true;
}

void Shutdown() {
    MH_DisableHook(MH_ALL_HOOKS);
    MH_Uninitialize();

    if (g_hwnd && oWndProc)
        SetWindowLongPtrW(g_hwnd, GWLP_WNDPROC, (LONG_PTR)oWndProc);

    ImGui_ImplDX11_Shutdown();
    ImGui_ImplWin32_Shutdown();
    ImGui::DestroyContext();

    if (g_rtv) { g_rtv->Release(); g_rtv = nullptr; }
}

} // namespace Hooks
