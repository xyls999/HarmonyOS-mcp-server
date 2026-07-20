# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HarmonyOS smart home app (智能家居) targeting HarmonyOS NEXT (SDK 6.1.1, API 24). Single-module phone app with four tabs: Home, Monitor, AI Chat, and Profile. Built with ArkTS/ArkUI declarative framework. All backend APIs are currently mocked — the app runs entirely on local preview data.

## Build & Run

This project uses DevEco Studio with the Hvigor build system. There is no CLI-only build workflow — use DevEco Studio to build, preview, and deploy:

- **Build**: DevEco Studio → Build → Build Hap(s)/App(s)
- **Preview**: DevEco Studio → Previewer (phone profile)
- **Run on device/emulator**: DevEco Studio → Run (requires signing config in `build-profile.json5`)
- **Lint**: Code Linter runs automatically in DevEco Studio; config in `code-linter.json5` (targets `*.ets`, enforces `@performance/recommended`, `@typescript-eslint/recommended`, and HarmonyOS security rules)
- **Tests**: Unit tests via `@ohos/hypium` in `entry/src/test/`; instrument tests in `entry/src/ohosTest/`

## Architecture

### Module Structure

Single `entry` module (HAP type). Entry point: `EntryAbility` → loads `pages/Index`.

### Source Layout (`entry/src/main/ets/`)

```
api/           API layer — static async methods wrapping mock data
  types.ets    All data models (Device, Sensor, Camera, ChatMessage, UserProfile, etc.)
  deviceApi    Device CRUD + control (fan/AC/door/light)
  sensorApi    Sensor queries + realtime subscription (WebSocket planned)
  monitorApi   Camera + alert messages
  chatApi      LLM chat with streaming (SSE planned)
  userApi      User profile + server status
components/    Reusable UI components (DeviceCard, SensorCard, ChatBubble, StatRing, etc.)
pages/         Tab pages (HomePage, MonitorPage, ChatPage, MinePage)
pages/detail/  Detail pages (DeviceDetailPage, SensorDetailPage, CameraDetailPage)
mock/          MockData class — single source of all preview data
theme/         Design tokens: Colors, Spacing, Typography, Effects
effects/       AnimatedNumber component
entryability/  App lifecycle (EntryAbility)
```

### Key Patterns

**API layer contract**: Every API class (`DeviceApi`, `SensorApi`, etc.) returns `MockData` via `delay()` wrappers. When connecting to a real backend, only replace the function bodies — signatures and return types stay the same. Pages never import `MockData` directly; they go through the API layer.

**Backend API endpoints**: Each API file documents the planned REST/WebSocket contract in header comments (e.g., `GET /api/devices`, `WS ws://host/sensors/realtime`, `POST /api/chat/send` with SSE streaming). These define the integration contract.

**Communication protocols**: The app distinguishes WiFi and StarFlash (星闪) channels. Device/sensor models carry a `protocol` field that determines which transport to use.

**Design system**: All colors, spacing, font sizes, and radii are centralized in `theme/`. Components use `AppColors`, `AppSpace`, `AppFont` constants — never hardcode style values. The visual style is "classic HarmonyOS light" (white cards, light gray background, system blue accent `#007DFF`).

**Page routing**: `main_pages.json` only declares `pages/Index`. The `Index` page manages tab switching via `@State currentIndex` — detail pages are embedded as child components, not NavRouter destinations.

## Language Notes

- Source files use `.ets` (extended TypeScript for ArkUI). ArkUI decorators: `@Entry`, `@Component`, `@State`, `@Builder`, `@Prop`, `@Link`.
- UI uses Chinese labels throughout (首页, 监控, 我的, etc.).
- Comments and doc strings are in Chinese.
