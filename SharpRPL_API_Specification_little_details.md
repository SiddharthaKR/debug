# SharpRPL — API Specification

*Consolidated from the project README and API docs. Sections marked **(to confirm)** are inferred or were not fully shown in source and should be verified against the code.*

---

## 1. Overview

SharpRPL is a Red Pitaya waveform acquisition and visualization system. A native sender on the Red Pitaya streams fixed-size binary sample packets over TCP to an ASP.NET Core server, which manages up to four device sessions simultaneously, re-streams each device's packets to the browser over WebSocket, and exposes HTTP APIs for session management, output/generator control, decimation, and raw memory (register) read/write.

The primary server is **`WebServer.FourDevice`**. In actual operation the primary UI is the browser UI served by that project.

---

## 2. Solution structure

| Project | Role |
|---|---|
| `WebServer.FourDevice/` | Primary server. Multi-device session management, WebSocket streaming, output control, discovery, memory R/W. |
| `WebServer.OneDevice/` | Compatibility server; name retained, but implementation and APIs aligned with the FourDevice line. Original PoC. |
| `RedPitaya.NativeC/` | Native sender running on the Red Pitaya. Acquires raw ADC samples, packs them into fixed-length binary packets, sends over TCP. Minimal data-transfer + control implementation. |
| `SharpRPL.Client/` | MAUI Hybrid-Blazor client scaffold, kept for validation. |

The MAUI Hybrid-Blazor approach still exists, but the browser-based UI is the primary implementation.

---

## 3. Runtime environment

| Property | Value |
|---|---|
| Target framework | `net10.0` |
| SDK verified in workspace | `10.0.203` |
| `global.json` | not present |
| Nullable | enabled |
| Implicit usings | enabled |
| AssemblyName / RootNamespace | `WebServer.FourDevice` |
| Web stack | ASP.NET Core Web SDK, Minimal API |
| NuGet | `SSH.NET` `2024.2.0` — used by `RedPitayaSshRunner` to start `run.sh` on the Red Pitaya over SSH |

---

## 4. Architecture / data flow

```
[Red Pitaya (Native-C)]
        │  fixed-size binary packets / TCP
        ▼
[WebServer.FourDevice (ASP.NET Core)]
        │  binary WebSocket, per deviceId
        ▼
[Browser UI]
```

Server responsibilities:

- Receive fixed-size Red Pitaya packets over TCP (one TCP session = one device).
- Keep multiple device sessions for up to four waveform panels.
- Stream per-device packets via `/ws/wave?deviceId=…`.
- Control acquisition decimation and output waveforms via API.
- Discover Red Pitaya devices and store a candidate list.
- On TCP connection failure, attempt SSH startup of `run.sh` on the board.

Native-C (`RedPitaya.NativeC`) command set: `OUT`, `DEC`, `ACQ`, `MEMR`, `MEMW`.

---

## 5. Wire protocol — packet format

Fixed-length structure, **little-endian**.

```c
#include <stdint.h>

#define RP_PACKET_SAMPLES 2048
#define RP_PACKET_MAGIC   0xDEADBEEF

#pragma pack(push, 1)
typedef struct rp_packet_t {
    uint32_t magic;         /* 0xDEADBEEF                     */
    uint32_t sequence_num;
    uint16_t channel;
    uint16_t decimation;
    uint32_t reserved;
    int16_t  data[RP_PACKET_SAMPLES];
} rp_packet_t;
#pragma pack(pop)
```

Byte layout:

| Offset | Field | Type |
|---|---|---|
| 0–3 | `magic` | UInt32 |
| 4–7 | `sequence_num` | UInt32 |
| 8–9 | `channel` | UInt16 |
| 10–11 | `decimation` | UInt16 |
| 12–15 | `reserved` | UInt32 |
| 16+ | `data` | Int16 × `PacketSamples` |

| Quantity | Value |
|---|---|
| Samples per packet (default) | 2048 |
| Header size | 16 bytes |
| Data size | 2048 × 2 = 4096 bytes |
| Total packet size | 4112 bytes |

Total size generalizes to `16 + PacketSamples * 2` bytes.

---

## 6. HTTP API reference

Base: the server's listen address (e.g. `http://localhost:5000` **(to confirm — port from `listenPort` in `/api/status`)**).

### 6.1 Status & discovery

#### `GET /api/status`
Returns current status including `deviceState`, `lastError`, `listenPort`, `connectionMode`, `targetHost`, `targetPort`, `activeDeviceId`, `sessions`, `packetSamples`, `magic`, latest packet info, and output states.

> `activeDeviceId` is for UI selection sync only. Acquisition can run on multiple sessions simultaneously.

#### `GET /api/devices/sessions`
Returns the registered session list and `activeDeviceId`.

### 6.2 Session management

#### `POST /api/devices/open`
Opens a session for the specified `deviceId` and target host.

Request body:
```json
{
  "deviceId": "rp-1",
  "targetHost": "192.168.128.125",
  "targetPort": 9000
}
```

#### `POST /api/devices/{deviceId}/close`
Closes the specified session.

#### `POST /api/devices/active`
Switches the active device session.

Request body:
```json
{ "deviceId": "rp-1" }
```

### 6.3 Output / generator control

#### `GET /api/output/status?deviceId=…`
Returns output status for the specified device. If `deviceId` is omitted, the active device is used.

#### `POST /api/output/{channel}/configure?deviceId=…`
Configures output on channel `1` or `2`.

Request body: **(to confirm — schema not shown in source; see `Models/OutputChannelModels.cs`.)**

### 6.4 Decimation control

Acquisition decimation is controllable via API (mouse-wheel in the UI maps to it). **(to confirm — exact route/body not shown in source.)**

### 6.5 Memory (register) read/write

#### `POST /api/device/memory/read?deviceId=…`
Sends a memory read command.

Request body:
```json
{ "address": "0x40000000" }
```
Response: **(to confirm — value field/shape not shown in source.)**

#### `POST /api/device/memory/write?deviceId=…`
Sends a memory write command.

Request body:
```json
{
  "address": "0x40000000",
  "value": "0x00000001"
}
```

---

## 7. WebSocket API

#### `WS /ws/wave?deviceId=…`
Streams raw `RpPacket.RawPacket` as binary for the specified device. The `deviceId` query parameter is **required**. Frame format is the little-endian packet in §5.

---

## 8. Register catalog — `seeting.json`

Named-register catalog consumed against the memory R/W API. Top-level:

| Key | Meaning |
|---|---|
| `version` | Schema version (currently `1`). |
| `endianness` | `little`. |
| `aliases` | Map of register **name → hex address**, e.g. `"PI_SET_KP": "0x40330108"`. |
| `registers` | Array of typed entries. Each entry's `address` field holds an **alias name** (resolved through `aliases`), plus `type`, optional `format`, and a default `value`. |

Register entry example:
```json
{ "address": "BPF_B0", "type": "q", "format": "Q15.16", "value": 0.0 }
```

Types observed:

| `type` | Meaning | `format` |
|---|---|---|
| `uint32` | Raw 32-bit word (decimal or hex string default). | — |
| `q` | Fixed-point. | `Q15.16`, `Q1.23` |
| `float` | IEEE-754 single. | — |

Register blocks present: `BPF_*` (bandpass filter: control, biquad coeffs `B0..A2`, state `S00/S01/S10/S11`, `MCOS/MSIN`), `SVF_*` (state-variable filter), `MIX_*` (mixer: control, phase increment, beta, manual phase offset), `LPF2_*`, `PI_*` (PID: setpoint, Kp/Ki/Kd, out min/max, control, auto-reset), `HPF0_*`/`HPF1_*`, and select/mux aliases (`LPF0_SEL`, `HPF1_SEL`, `SCOPE0_SEL`, etc.).

> **Known issue (deferred):** the `aliases` block contains four consecutive keys all named `BPF_S00`; JSON last-wins collapses them, so `BPF_S01`/`BPF_S10`/`BPF_S11` do not resolve. There is also an address overlap with `BPF_MCOS`/`BPF_MSIN`. Not fixed yet.

---

## 9. Internal services & implementation notes

| Component | Responsibility |
|---|---|
| `PacketHub` | Keeps the latest packet and per-device channels. |
| `RedPitayaIngestService` | TCP connect/reconnect, multi-session acquisition activation, active-device switching, SSH auto-start. |
| `RedPitayaDiscoveryService` | Stores scan results in `data/redpitaya_list.json`. |
| `RedPitayaSshRunner` | Executes `SshRunCommand` via SSH.NET (starts `run.sh`). |
| Ingest buffering | Incoming frames are buffered in a bounded channel. |
| Frontend | Tile layout and panel-device linking in `wwwroot/index.html` and `wwwroot/app.js`. |

Related files: `Program.cs`, `Models/DeviceOptions.cs`, `Models/RpPacket.cs`, `Models/OutputChannelModels.cs`, `Services/PacketHub.cs`, `Services/RedPitayaIngestService.cs`, `Services/RedPitayaDiscoveryService.cs`, `Services/RedPitayaSshRunner.cs`, `wwwroot/index.html`, `wwwroot/app.js`, `data/redpitaya_list.json`.

---

## 10. Browser UI behavior

- Display modes: single device, 2-row, 2-column, 2×2.
- Per-tile device assignment via dropdown; devices assigned independently to each tile.
- Selecting a tile links the right-side settings (Generator / Memory Access) panel to that device.
- Mouse wheel: change decimation.
- Shift + mouse wheel: change vertical scale (`mV/div`).
- Left drag: change Y offset (`Yoff`).
- In 2-column mode (`1x2`), rendered samples are reduced to 1024 for lower drawing load.

---

## 11. Open items to confirm against code

1. Server listen port (from `listenPort` in `/api/status`).
2. `POST /api/output/{channel}/configure` request body schema (`Models/OutputChannelModels.cs`).
3. Decimation control endpoint route and body.
4. `POST /api/device/memory/read` response shape (where the read-back value lives).
5. Whether `targetPort` `9000` in the open example is the fixed Native-C port or per-deployment.