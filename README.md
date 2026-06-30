# RDP Gateway

This is an experimental local compatibility layer for Microsoft Remote Desktop / Windows App, designed to route RDP traffic outbound through a SOCKS5 proxy. It allows RDP connections to go through encrypted proxies such as Clash, avoiding the security risks of exposing the RDP port directly to the internet, such as brute-force attacks.

[简体中文](README.cn.md)

## Quick Start

* [Download latest version](https://github.com/OnionJuice/RDP_Gateway/releases/download/v1.0.0/RDP.Gateway_v1.0.0.zip)
* Copy **RDP Gateway** to the **Applications** folder. If you encounter the message “cannot verify the developer”, run the following commands:
```shell
xattr -dr com.apple.quarantine "/Applications/RDP Gateway.app"
codesign --force --deep --sign - "/Applications/RDP Gateway.app"
```
* Modify the gateway username and password, and enter the SOCKS5 proxy port, for example Clash’s port `7890`.
* Click **Generate localhost Certificate**.
* Click **Trust Certificate in macOS**. This step is optional. If the certificate is not trusted, you will simply need to click **Continue** once more each time you connect.
* Select the **Run** tab at the top, then click **Start Gateway**.
* In **Microsoft Remote Desktop / Windows App**, go to **Preferences** and add a gateway. Use the connection information configured above.
* In the client connection settings, select the corresponding gateway and check **Bypass for local addresses**.
* Save the configuration.

Connections will only be available through SOCKS5. The connection negotiation may take some time.

## What It Does

- Listens as a local HTTPS gateway, normally on `127.0.0.1:9443`.
- Accepts Microsoft Remote Desktop `RDG_OUT_DATA` / `RDG_IN_DATA` WebSocket gateway requests.
- Authenticates local gateway requests with either Basic credentials or the `RDG-User-Id` header used by Microsoft Remote Desktop.
- Implements the minimal RDG WebSocket control flow:
  - handshake
  - tunnel create
  - tunnel authorization
  - channel create
  - data packets
  - keepalive and close-channel responses
- Decodes `CHANNEL_CREATE` to discover the real RDP host and port.
- Opens that host through a SOCKS5 proxy and relays RDP bytes both ways.
- Reassembles RDG packets across WebSocket frame boundaries before parsing.
- Also supports a simple HTTPS `CONNECT` tunnel path for compatible clients and tests.
- Provides a PyQt6 GUI with English/Chinese language switching, macOS menu bar residency, and automatic default language detection from macOS.

## Current Limits

- This is not a full enterprise RD Gateway replacement.
- Keep it bound to `127.0.0.1` unless you are deliberately hardening it.
- Legacy `RPC_IN_DATA` / `RPC_OUT_DATA` transport still returns `501 Not Implemented`.
- SOCKS5 outbound currently supports no-auth SOCKS5.
- The gateway password is only used for Basic-auth clients. Microsoft Remote Desktop for macOS may authenticate the WebSocket path by sending `RDG-User-Id`, which is matched against `gateway.username`.

## Requirements

- macOS
- `uv`
- Python managed by `uv`
- OpenSSL, used by `scripts/gen_cert.sh`
- A running SOCKS5 proxy, for example on `127.0.0.1:1080`
- Microsoft Remote Desktop

The GUI app additionally uses PyQt6. The macOS `.app` bundle produced by the build script includes Python and PyQt6, so users of the bundled app do not need to install Python separately.

## Install

The project uses `uv` for virtual environment and dependency management. The checked-in `uv.toml` defaults to the Tsinghua PyPI mirror.

```bash
cd /Users/jim/Documents/AI-Project/ops/RDP_Gateway
uv sync --default-index https://pypi.tuna.tsinghua.edu.cn/simple
```

If the Tsinghua mirror is slow, use Aliyun:

```bash
uv sync --default-index https://mirrors.aliyun.com/pypi/simple/
```

## Configure

Create a local config file:

```bash
cp config.example.toml config.toml
```

Edit `config.toml` as needed:

```toml
[gateway]
listen_host = "127.0.0.1"
listen_port = 9443
username = "rdg"
password = "change-me"
cert_file = "certs/localhost.pem"
key_file = "certs/localhost-key.pem"
read_timeout_seconds = 20

[socks5]
host = "127.0.0.1"
port = 1080
connect_timeout_seconds = 20

[logging]
level = "INFO"

[app]
start_gateway_on_launch = false
launch_at_login = false
keep_in_menu_bar = false
language = "auto"
```

Generate a localhost certificate:

```bash
./scripts/gen_cert.sh
```

Trust the certificate on macOS:

```bash
./scripts/trust_cert_macos.sh
```

The trust script and GUI add the certificate to the current user's login keychain with SSL trust. This avoids administrator prompts and is enough for the local single-user workflow.

## GUI App

Run the PyQt6 GUI from source:

```bash
uv run rdp-gateway-gui --config config.toml
```

The GUI can:

- edit and persist all `config.toml` gateway, SOCKS5, certificate, logging, and app settings
- show or hide the gateway password while editing it
- generate a localhost certificate
- ask macOS to trust the certificate
- start and stop the gateway process
- enable launch at login through a user LaunchAgent
- keep the app resident in the macOS menu bar, hide the window on close, and quit explicitly from the UI or menu bar menu
- reopen the already-running instance when the app is launched again
- switch the interface language between Auto, English, and Chinese

When running from source, the default config is `config.toml` in the project directory. When running from the bundled macOS app, the default config is:

```text
~/Library/Application Support/RDP_Gateway/config.toml
```

The launch-at-login option writes:

```text
~/Library/LaunchAgents/local.rdp-gateway.app.plist
```

`[app].keep_in_menu_bar = true` enables the menu bar status item. With that option enabled, closing the window only hides it; the gateway keeps running if it was started. Use the menu bar icon or launch the app again to show the configuration window. Use the `Quit App` button or the menu bar `Quit App` item to fully exit.

The GUI language is stored in `[app].language`. Supported values are:

- `auto`: follow the macOS system language, using Chinese for Chinese-language systems and English otherwise
- `en`: force English
- `zh`: force Chinese

## Run From CLI

Start your SOCKS5 proxy first, then start the gateway:

```bash
./scripts/run.sh
```

Equivalent direct command:

```bash
uv run rdp-gateway --config config.toml
```

A successful startup log looks like:

```text
RDP gateway shim listening on ('127.0.0.1', 9443)
```

## Build The macOS App

Build the app bundle:

```bash
./scripts/build_macos_app.sh
```

The script:

- syncs dependencies with `uv`
- builds `dist/RDP Gateway.app` with PyInstaller
- applies an ad-hoc code signature
- removes the `com.apple.quarantine` attribute when present

The current build output is:

```text
dist/RDP Gateway.app
```

If macOS still says the app is damaged or cannot be opened, run:

```bash
xattr -dr com.apple.quarantine "dist/RDP Gateway.app"
codesign --force --deep --sign - "dist/RDP Gateway.app"
```

If Gatekeeper blocks the app, open it once from Finder with Control-click -> Open, or review it in System Settings -> Privacy & Security. For distribution to other machines, use a real Developer ID certificate and notarization.

## Microsoft Remote Desktop Setup

In Microsoft Remote Desktop, configure the PC entry like this:

- PC name: the real RDP target, for example `192.168.0.9:3389`
- Gateway: `127.0.0.1:9443`
- Gateway username: `gateway.username` from `config.toml`, for example `rdg`
- Gateway password: `gateway.password` from `config.toml`

When the flow is working, logs should show:

```text
RD Gateway packet PKT_TYPE_HANDSHAKE_REQUEST
RD Gateway packet PKT_TYPE_TUNNEL_CREATE
RD Gateway packet PKT_TYPE_TUNNEL_AUTH
RD Gateway packet PKT_TYPE_CHANNEL_CREATE
RD Gateway channel create target=...:3389
opening RDG SOCKS5 tunnel ...
RD Gateway channel open target=...:3389
```

## Troubleshooting

### Stuck at "securing connection to gateway"

Check whether Microsoft Remote Desktop reaches the gateway:

```text
incoming gateway request ... method=RDG_OUT_DATA
```

If there is no request, verify the gateway address, TLS certificate trust, and local firewall rules.

### Authentication failed with missing credentials

Microsoft Remote Desktop may not send Basic credentials on the WebSocket path. The gateway accepts `RDG-User-Id` when it decodes to `gateway.username`. Make sure the Gateway username in Microsoft Remote Desktop matches `gateway.username`.

### SOCKS5 connection failed

Verify `[socks5] host` and `port`, and confirm the SOCKS5 proxy can reach the real RDP host.

### Gateway failed with FileNotFoundError

The GUI reports the missing path explicitly, for example:

```text
Gateway failed: FileNotFoundError: missing file: /path/to/certs/localhost.pem (TLS certificate file not found)
```

If the certificate or private key is missing, generate a localhost certificate from the GUI or run `./scripts/gen_cert.sh`, then verify `[gateway].cert_file` and `[gateway].key_file`.

### Certificate trust failed

When the GUI asks macOS to trust the certificate, it runs `security add-trusted-cert` against the current user's login keychain. If this fails, the error dialog includes the certificate path, keychain path, exit status, macOS reason, and the exact `security` command.

Common causes are:

- the certificate path is wrong or the certificate was not generated
- the login keychain is locked or unavailable
- macOS refused updating the user's trust settings

You can retry from the GUI, unlock the login keychain in Keychain Access, or run the command shown in the error dialog manually in Terminal to see the same macOS error.

### The macOS app appears to flash and close

One known cause was the automatic language detector referencing Qt language enum values that are not present in every PyQt6 build. Since the GUI starts with `[app].language = "auto"` by default, that could raise an `AttributeError` during window creation and make the app appear to flash-close from Finder. The detector now checks enum availability before using those values.

Another cause happens when launch-at-login already started the app. Launching the app again used to create a second instance. That second instance could immediately fail when it tried to bind the same gateway address, usually `127.0.0.1:9443`, which also looks like a flash-close from Finder.

The GUI now uses a single-instance local socket. When an instance is already running, launching the app again asks the existing process to show the configuration window and then exits the second process.

When `[app].keep_in_menu_bar = true`, closing the window hides it to the macOS menu bar instead of quitting. Use `Quit App` to fully exit the process.

### Repeated reconnects after a successful login

This project reassembles RDG packets across WebSocket frame boundaries. If reconnects still happen, look for warnings such as:

```text
RD Gateway WebSocket probe failed
RDG packet length mismatch
RDG DATA received before channel is open
```

Send the warning and the preceding `PKT_TYPE_...` lines when debugging.

## Development

Run tests:

```bash
uv run pytest
```

The test suite covers:

- TOML config parsing
- config persistence for GUI app settings
- GUI language selection and default language resolution
- menu bar residency configuration
- LaunchAgent plist generation
- Basic and `RDG-User-Id` authentication
- SOCKS5 CONNECT
- TCP relay behavior
- WebSocket frame handling
- RDG packet parsing, construction, and fragmented-packet reassembly

## Security Notes

- Keep `listen_host = "127.0.0.1"` for normal use.
- Do not commit `config.toml`, generated certs, private keys, `.venv`, cache directories, or logs.
- Do not reuse important passwords in `config.toml`.
- Logs avoid printing passwords and full RDP payloads.
