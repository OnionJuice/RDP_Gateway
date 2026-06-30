# RDP Gateway

这是一个实验性的本地 Microsoft Remote Desktop / Windows App 兼容层，用来让 RDP 流量通过 SOCKS5 代理出站。让RDP通过例如Clash等加密代理连接，避免需要暴露RDP端口带来的破解或安全风险。

## 快速使用
- 下载：[下载最新版](https://github.com/OnionJuice/RDP_Gateway/releases/download/v1.0.0/RDP.Gateway_v1.0.0.zip)
- 将RDP Gateway 复制到 应用程序目录，如果遇到“无法验证开发者” 则执行
```shell
xattr -dr com.apple.quarantine "/Applications/RDP Gateway.app"
codesign --force --deep --sign - "/Applications/RDP Gateway.app"
```
- 修改网关用户名，密码，填写SOCKS5代理端口（例如Clash的端口7890）
- 点击生成localhost证书
- 点击在macOS中信任证书（可选），不信任只会每次进入都需要多点一次Continue而已
- 选顶部 运行 标签，点击启动网关
- 在Microsoft Remote Desktop / Windows App 中的 Preferences中添加 Gateways，连接信息如刚配置的网关信息。
- 在客户端连接信息中，选用对应的网关，并勾选 Bypass for local addresses
- 保存仅可通过SOCKS5连接，连接协商需等待一段时间。

## 功能

- 作为本地 HTTPS Gateway 监听，默认地址为 `127.0.0.1:9443`。
- 接受 Microsoft Remote Desktop 发起的 `RDG_OUT_DATA` / `RDG_IN_DATA` WebSocket Gateway 请求。
- 支持 Basic 凭据认证，也支持 Microsoft Remote Desktop WebSocket 路径使用的 `RDG-User-Id` 头。
- 实现最小 RDG WebSocket 控制流程：
  - handshake
  - tunnel create
  - tunnel authorization
  - channel create
  - data packets
  - keepalive 和 close-channel 响应
- 解析 `CHANNEL_CREATE` 获取真实 RDP 主机和端口。
- 通过 SOCKS5 代理连接真实 RDP 主机，并双向转发 RDP 数据。
- 在解析 RDG 包前，会跨 WebSocket frame 重组 RDG packet。
- 另外保留一个简单 HTTPS `CONNECT` 隧道路径，供兼容客户端和测试使用。
- 提供 PyQt6 GUI，支持中英文切换、macOS 顶部状态栏驻留，并可根据 macOS 系统语言自动选择默认显示语言。

## 当前限制

- 这不是完整的企业级 RD Gateway 替代品。
- 正常使用时请保持监听在 `127.0.0.1`，不要暴露到局域网或公网。
- 旧式 `RPC_IN_DATA` / `RPC_OUT_DATA` 传输仍会返回 `501 Not Implemented`。
- SOCKS5 出站目前支持无认证 SOCKS5。
- `gateway.password` 只用于 Basic 认证客户端。macOS 版 Microsoft Remote Desktop 的 WebSocket 路径可能发送 `RDG-User-Id`，本程序会把它解码后与 `gateway.username` 匹配。

## 环境要求

- macOS
- `uv`
- 由 `uv` 管理的 Python 环境
- OpenSSL，用于 `scripts/gen_cert.sh`
- 一个运行中的 SOCKS5 代理，例如 `127.0.0.1:1080`
- Microsoft Remote Desktop

GUI App 额外使用 PyQt6。通过打包脚本生成的 macOS `.app` 会包含 Python 和 PyQt6，因此使用打包版 App 时不需要单独安装 Python。

## 安装

项目使用 `uv` 管理虚拟环境和依赖。仓库中的 `uv.toml` 默认使用清华 PyPI 镜像。

```bash
cd /Users/jim/Documents/AI-Project/ops/RDP_Gateway
uv sync --default-index https://pypi.tuna.tsinghua.edu.cn/simple
```

如果清华镜像较慢，可以换用阿里云镜像：

```bash
uv sync --default-index https://mirrors.aliyun.com/pypi/simple/
```

## 配置

创建本地配置文件：

```bash
cp config.example.toml config.toml
```

按需编辑 `config.toml`：

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

生成 localhost 证书：

```bash
./scripts/gen_cert.sh
```

在 macOS 上信任该证书：

```bash
./scripts/trust_cert_macos.sh
```

信任脚本和 GUI 会把证书加入当前用户的 login keychain，并设置 SSL 信任。这样不需要管理员提权，适合本机单用户使用场景。

## GUI App

从源码运行 PyQt6 GUI：

```bash
uv run rdp-gateway-gui --config config.toml
```

GUI 可以：

- 编辑并持久化 `config.toml` 中的 gateway、SOCKS5、证书、日志和 app 设置
- 编辑网关密码时显示或隐藏密码
- 生成 localhost 证书
- 请求 macOS 信任证书
- 启动和停止 gateway
- 通过用户级 LaunchAgent 启用开机登录启动
- 驻留在 macOS 顶部状态栏，关闭窗口时隐藏窗口，并可从 UI 或状态栏菜单显式退出
- 再次打开 App 时唤醒已经运行的实例并显示配置界面
- 在自动、English、中文之间切换界面语言

从源码运行时，默认配置文件是项目目录下的 `config.toml`。运行打包后的 macOS App 时，默认配置文件是：

```text
~/Library/Application Support/RDP_Gateway/config.toml
```

开机登录启动会写入：

```text
~/Library/LaunchAgents/local.rdp-gateway.app.plist
```

`[app].keep_in_menu_bar = true` 会启用顶部状态栏图标。启用后，关闭窗口只会隐藏窗口；如果 gateway 已启动，它会继续运行。可以通过顶部状态栏图标或再次打开 App 来显示配置界面。要完全退出进程，请使用 `退出程序` 按钮或顶部状态栏菜单中的 `退出程序`。

GUI 语言会保存到 `[app].language`。支持的值为：

- `auto`：跟随 macOS 系统语言；中文系统使用中文，其他语言默认使用英文
- `en`：强制使用英文
- `zh`：强制使用中文

## 命令行运行

先启动 SOCKS5 代理，再启动 Gateway：

```bash
./scripts/run.sh
```

等价的直接命令：

```bash
uv run rdp-gateway --config config.toml
```

启动成功后会看到类似日志：

```text
RDP gateway shim listening on ('127.0.0.1', 9443)
```

## 打包 macOS App

构建 App bundle：

```bash
./scripts/build_macos_app.sh
```

该脚本会：

- 使用 `uv` 同步依赖
- 使用 PyInstaller 构建 `dist/RDP Gateway.app`
- 执行 ad-hoc 签名
- 在存在 `com.apple.quarantine` 属性时移除该属性

当前构建产物为：

```text
dist/RDP Gateway.app
```

如果 macOS 仍提示 App 已损坏或无法打开，运行：

```bash
xattr -dr com.apple.quarantine "dist/RDP Gateway.app"
codesign --force --deep --sign - "dist/RDP Gateway.app"
```

如果被 Gatekeeper 阻止，可以在 Finder 中按住 Control 点击 App 并选择“打开”，或在“系统设置 -> 隐私与安全性”中允许打开。若要分发给其他机器，应使用正式 Developer ID 证书并进行 notarization。

## Microsoft Remote Desktop 配置

在 Microsoft Remote Desktop 的 PC 条目中这样配置：

- PC name：真实 RDP 目标，例如 `192.168.0.9:3389`
- Gateway：`127.0.0.1:9443`
- Gateway username：`config.toml` 中的 `gateway.username`，例如 `rdg`
- Gateway password：`config.toml` 中的 `gateway.password`

流程正常时，日志应出现：

```text
RD Gateway packet PKT_TYPE_HANDSHAKE_REQUEST
RD Gateway packet PKT_TYPE_TUNNEL_CREATE
RD Gateway packet PKT_TYPE_TUNNEL_AUTH
RD Gateway packet PKT_TYPE_CHANNEL_CREATE
RD Gateway channel create target=...:3389
opening RDG SOCKS5 tunnel ...
RD Gateway channel open target=...:3389
```

## 排障

### 卡在 "securing connection to gateway"

先确认 Microsoft Remote Desktop 是否连到了 Gateway：

```text
incoming gateway request ... method=RDG_OUT_DATA
```

如果没有这类请求，请检查 Gateway 地址、TLS 证书信任状态以及本机防火墙规则。

### 提示缺少认证信息

Microsoft Remote Desktop 在 WebSocket 路径上可能不会发送 Basic 凭据。此时本程序会接受 `RDG-User-Id`，并将其解码后与 `gateway.username` 比对。请确认 Microsoft Remote Desktop 中填写的 Gateway 用户名与 `config.toml` 中的 `gateway.username` 一致。

### SOCKS5 连接失败

检查 `[socks5] host` 和 `port`，并确认 SOCKS5 代理能够访问真实 RDP 主机。

### Gateway failed 显示 FileNotFoundError

GUI 会明确显示缺失的文件路径，例如：

```text
Gateway failed: FileNotFoundError: missing file: /path/to/certs/localhost.pem (TLS certificate file not found)
```

如果缺少证书或私钥，可以在 GUI 中生成 localhost 证书，或运行 `./scripts/gen_cert.sh`，然后确认 `[gateway].cert_file` 和 `[gateway].key_file` 配置正确。

### 证书信任失败

GUI 请求 macOS 信任证书时，会针对当前用户的 login keychain 运行 `security add-trusted-cert`。如果失败，错误弹窗会显示证书路径、keychain 路径、退出码、macOS 返回原因，以及实际执行的 `security` 命令。

常见原因包括：

- 证书路径不正确，或还没有生成证书
- login keychain 被锁定或不可用
- macOS 拒绝更新当前用户的证书信任设置

可以在 GUI 中重试，在“钥匙串访问”中解锁 login keychain，或把错误弹窗里的命令复制到 Terminal 手动运行，查看同样的 macOS 错误。

### macOS App 看起来闪一下就关闭

一个已知原因是自动语言判断引用了部分 PyQt6 构建中不存在的 Qt 语言枚举。GUI 默认使用 `[app].language = "auto"`，因此窗口创建阶段可能直接抛出 `AttributeError`，从 Finder 看起来就像闪退。现在语言判断会先检查枚举是否存在，再使用对应值。

另一个原因是开机登录项已经启动了 App。再次打开 App 时，旧版本会创建第二个实例。第二个实例如果继续尝试绑定同一个 gateway 地址，通常是 `127.0.0.1:9443`，会因为端口已被占用而立刻失败；从 Finder 看起来同样像闪退。

现在 GUI 使用本机单实例 socket。已有实例运行时，再次打开 App 会通知已有进程显示配置界面，然后第二个进程会自行退出。

当 `[app].keep_in_menu_bar = true` 时，关闭窗口会隐藏到 macOS 顶部状态栏，而不是退出程序。需要完全退出时，请使用 `退出程序`。

### 登录成功后反复断线重连

本程序会跨 WebSocket frame 重组 RDG packet。如果仍然反复重连，请关注以下日志：

```text
RD Gateway WebSocket probe failed
RDG packet length mismatch
RDG DATA received before channel is open
```

排查时请保留 warning 以及它之前的 `PKT_TYPE_...` 日志。

## 开发

运行测试：

```bash
uv run pytest
```

测试覆盖：

- TOML 配置解析
- GUI app 设置的配置持久化
- GUI 语言选择和默认语言解析
- 顶部状态栏驻留配置
- LaunchAgent plist 生成
- Basic 和 `RDG-User-Id` 认证
- SOCKS5 CONNECT
- TCP relay 行为
- WebSocket frame 处理
- RDG packet 解析、构造和拆包重组

## 安全说明

- 常规使用时保持 `listen_host = "127.0.0.1"`。
- 不要提交 `config.toml`、生成的证书、私钥、`.venv`、缓存目录或日志。
- 不要在 `config.toml` 中复用重要密码。
- 日志避免输出密码和完整 RDP payload。
