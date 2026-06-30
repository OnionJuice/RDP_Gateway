from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QLocale, QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .cert_utils import generate_localhost_cert, trust_cert_macos
from .config import load_config
from .config_file import default_config_path, ensure_config, load_raw_config, save_raw_config
from .launch_agent import install as install_launch_agent
from .launch_agent import is_installed as is_launch_agent_installed
from .launch_agent import uninstall as uninstall_launch_agent
from .server import RdpGatewayServer


LANG_AUTO = "auto"
LANG_EN = "en"
LANG_ZH = "zh"
SINGLE_INSTANCE_SERVER = "local.rdp-gateway.gui"
SINGLE_INSTANCE_SHOW_COMMAND = b"show\n"

TEXT: dict[str, dict[str, str]] = {
    LANG_EN: {
        "window_title": "RDP Gateway",
        "tab_config": "Configuration",
        "tab_runtime": "Runtime",
        "save": "Save",
        "reload": "Reload",
        "config_file": "Config file:",
        "gateway": "Gateway",
        "listen_host": "Listen host",
        "listen_port": "Listen port",
        "gateway_username": "Gateway username",
        "gateway_password": "Gateway password",
        "show_password": "Show",
        "hide_password": "Hide",
        "read_timeout": "Read timeout seconds",
        "certificate": "Certificate",
        "certificate_file": "Certificate file",
        "key_file": "Key file",
        "browse": "Browse",
        "generate_cert": "Generate Localhost Cert",
        "trust_cert": "Trust Cert on macOS",
        "private_key": "Private key",
        "socks_host": "SOCKS5 host",
        "socks_port": "SOCKS5 port",
        "connect_timeout": "Connect timeout seconds",
        "app": "App",
        "language": "Language",
        "log_level": "Log level",
        "start_on_launch": "Start gateway when the app opens",
        "launch_at_login": "Launch this app at login",
        "keep_in_menu_bar": "Keep this app in the macOS menu bar",
        "gateway_stopped": "Gateway stopped",
        "start_gateway": "Start Gateway",
        "stop_gateway": "Stop Gateway",
        "quit_app": "Quit App",
        "stopping_gateway": "Stopping gateway...",
        "config_loaded": "Configuration loaded.",
        "config_saved": "Configuration saved.",
        "load_failed": "Load failed",
        "save_failed": "Save failed",
        "cert_generated": "Localhost certificate generated.",
        "cert_gen_failed": "Certificate generation failed",
        "cert_trusted": "Certificate trusted by macOS.",
        "cert_trust_failed": "Certificate trust failed",
        "gateway_failed": "Gateway failed",
        "launch_enabled": "Launch at login enabled.",
        "launch_disabled": "Launch at login disabled.",
        "show_configuration": "Show Configuration",
        "tray_not_available": "macOS menu bar status item is not available.",
        "hidden_to_tray": "Window hidden. Use the menu bar icon to reopen or quit.",
        "language_auto": "Auto",
        "language_en": "English",
        "language_zh": "中文",
    },
    LANG_ZH: {
        "window_title": "RDP Gateway",
        "tab_config": "配置",
        "tab_runtime": "运行",
        "save": "保存",
        "reload": "重新加载",
        "config_file": "配置文件：",
        "gateway": "网关",
        "listen_host": "监听地址",
        "listen_port": "监听端口",
        "gateway_username": "网关用户名",
        "gateway_password": "网关密码",
        "show_password": "显示",
        "hide_password": "隐藏",
        "read_timeout": "读取超时秒数",
        "certificate": "证书",
        "certificate_file": "证书文件",
        "key_file": "私钥文件",
        "browse": "浏览",
        "generate_cert": "生成 localhost 证书",
        "trust_cert": "在 macOS 中信任证书",
        "private_key": "私钥",
        "socks_host": "SOCKS5 地址",
        "socks_port": "SOCKS5 端口",
        "connect_timeout": "连接超时秒数",
        "app": "应用",
        "language": "语言",
        "log_level": "日志级别",
        "start_on_launch": "打开应用时启动网关",
        "launch_at_login": "开机登录时启动此应用",
        "keep_in_menu_bar": "驻留在 macOS 顶部状态栏",
        "gateway_stopped": "网关已停止",
        "start_gateway": "启动网关",
        "stop_gateway": "停止网关",
        "quit_app": "退出程序",
        "stopping_gateway": "正在停止网关...",
        "config_loaded": "配置已加载。",
        "config_saved": "配置已保存。",
        "load_failed": "加载失败",
        "save_failed": "保存失败",
        "cert_generated": "localhost 证书已生成。",
        "cert_gen_failed": "证书生成失败",
        "cert_trusted": "证书已被 macOS 信任。",
        "cert_trust_failed": "证书信任失败",
        "gateway_failed": "网关失败",
        "launch_enabled": "已启用开机登录启动。",
        "launch_disabled": "已禁用开机登录启动。",
        "show_configuration": "打开配置界面",
        "tray_not_available": "macOS 顶部状态栏图标不可用。",
        "hidden_to_tray": "窗口已隐藏，可通过顶部状态栏图标重新打开或退出。",
        "language_auto": "自动",
        "language_en": "English",
        "language_zh": "中文",
    },
}


def resolve_language(value: str | None) -> str:
    if value in {LANG_EN, LANG_ZH}:
        return value
    language = QLocale.system().language()
    chinese_languages = {
        member
        for member in (
            getattr(QLocale.Language, "Chinese", None),
            getattr(QLocale.Language, "Cantonese", None),
            getattr(QLocale.Language, "MinNanChinese", None),
            getattr(QLocale.Language, "WuChinese", None),
        )
        if member is not None
    }
    if language in chinese_languages:
        return LANG_ZH
    return LANG_EN


class GatewayThread(QThread):
    status_changed = pyqtSignal(str)
    failed = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self._config_path = config_path
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            config = load_config(self._config_path)
            server = RdpGatewayServer(config)
            self._task = self._loop.create_task(server.serve_forever())
            self.status_changed.emit(
                f"Gateway running on {config.gateway.listen_host}:{config.gateway.listen_port}"
            )
            self._loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.failed.emit(format_gateway_exception(exc))
        finally:
            if self._loop is not None:
                pending = [task for task in asyncio.all_tasks(self._loop) if not task.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                self._loop.close()
            self.stopped.emit()

    def stop(self) -> None:
        if self._loop is None or self._task is None:
            return
        self._loop.call_soon_threadsafe(self._task.cancel)


def format_gateway_exception(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        filename = _missing_filename(exc)
        reason = exc.strerror or "No such file or directory"
        if filename:
            return f"FileNotFoundError: missing file: {filename} ({reason})"
        return f"FileNotFoundError: missing file ({reason})"
    return f"{exc.__class__.__name__}: {exc}"


def _missing_filename(exc: FileNotFoundError) -> str | None:
    filename = getattr(exc, "filename", None)
    if filename:
        return str(filename)
    for arg in exc.args:
        if isinstance(arg, os.PathLike):
            return os.fspath(arg)
        if isinstance(arg, str) and arg:
            return arg
    return None


class LogEmitter(QObject):
    message = pyqtSignal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, emitter: LogEmitter) -> None:
        super().__init__()
        self._emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        self._emitter.message.emit(self.format(record))


class MainWindow(QMainWindow):
    def __init__(self, config_path: Path, *, autostart: bool = False) -> None:
        super().__init__()
        self._config_path = config_path
        ensure_config(self._config_path)
        self._language = resolve_language(LANG_AUTO)
        self._loading_config = False
        self._really_quitting = False
        self._initial_visibility = "normal"
        self._gateway_thread: GatewayThread | None = None
        self._log_emitter = LogEmitter()
        self._log_handler = QtLogHandler(self._log_emitter)
        self._log_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logging.getLogger().addHandler(self._log_handler)
        logging.getLogger().setLevel(logging.INFO)

        self.resize(820, 720)
        self._build_ui()
        self._build_tray()
        self._retranslate()
        self._log_emitter.message.connect(self._append_log)
        self.load_config()
        if autostart or self.start_on_launch_checkbox.isChecked():
            self.start_gateway()
            if autostart:
                self._initial_visibility = (
                    "hidden"
                    if self.keep_in_menu_bar_checkbox.isChecked()
                    and QSystemTrayIcon.isSystemTrayAvailable()
                    else "minimized"
                )

    def _build_ui(self) -> None:
        self.tabs = QTabWidget()
        self.config_tab = self._build_config_tab()
        self.runtime_tab = self._build_runtime_tab()
        self.tabs.addTab(self.config_tab, "")
        self.tabs.addTab(self.runtime_tab, "")
        self.setCentralWidget(self.tabs)

        self.save_action = QAction(self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.triggered.connect(self.save_config)
        self.addAction(self.save_action)

    def _build_config_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        path_row = QHBoxLayout()
        self.config_path_label = QLabel(str(self._config_path))
        self.config_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.reload_button = QPushButton()
        self.reload_button.clicked.connect(self.load_config)
        self.save_button = QPushButton()
        self.save_button.clicked.connect(self.save_config)
        self.config_file_label = QLabel()
        path_row.addWidget(self.config_file_label)
        path_row.addWidget(self.config_path_label, 1)
        path_row.addWidget(self.reload_button)
        path_row.addWidget(self.save_button)
        layout.addLayout(path_row)

        self.gateway_group = QGroupBox()
        gateway_form = QFormLayout(self.gateway_group)
        self.listen_host = QLineEdit()
        self.listen_port = self._port_spinbox(9443)
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_visible = False
        self.password_row = QWidget()
        password_layout = QHBoxLayout(self.password_row)
        password_layout.setContentsMargins(0, 0, 0, 0)
        self.password_toggle_button = QPushButton()
        self.password_toggle_button.setCheckable(True)
        self.password_toggle_button.clicked.connect(self._toggle_password_visibility)
        password_layout.addWidget(self.password, 1)
        password_layout.addWidget(self.password_toggle_button)
        self.read_timeout = self._seconds_spinbox(20)
        self.listen_host_label = QLabel()
        self.listen_port_label = QLabel()
        self.username_label = QLabel()
        self.password_label = QLabel()
        self.read_timeout_label = QLabel()
        gateway_form.addRow(self.listen_host_label, self.listen_host)
        gateway_form.addRow(self.listen_port_label, self.listen_port)
        gateway_form.addRow(self.username_label, self.username)
        gateway_form.addRow(self.password_label, self.password_row)
        gateway_form.addRow(self.read_timeout_label, self.read_timeout)
        layout.addWidget(self.gateway_group)

        self.cert_group = QGroupBox()
        cert_layout = QGridLayout(self.cert_group)
        self.cert_file = QLineEdit()
        self.key_file = QLineEdit()
        self.cert_browse = QPushButton()
        self.cert_browse.clicked.connect(lambda: self._browse_file(self.cert_file, self.tr("certificate")))
        self.key_browse = QPushButton()
        self.key_browse.clicked.connect(lambda: self._browse_file(self.key_file, self.tr("private_key")))
        self.generate_button = QPushButton()
        self.generate_button.clicked.connect(self.generate_certificate)
        self.trust_button = QPushButton()
        self.trust_button.clicked.connect(self.trust_certificate)
        self.cert_file_label = QLabel()
        self.key_file_label = QLabel()
        cert_layout.addWidget(self.cert_file_label, 0, 0)
        cert_layout.addWidget(self.cert_file, 0, 1)
        cert_layout.addWidget(self.cert_browse, 0, 2)
        cert_layout.addWidget(self.key_file_label, 1, 0)
        cert_layout.addWidget(self.key_file, 1, 1)
        cert_layout.addWidget(self.key_browse, 1, 2)
        cert_layout.addWidget(self.generate_button, 2, 1)
        cert_layout.addWidget(self.trust_button, 2, 2)
        layout.addWidget(self.cert_group)

        socks_group = QGroupBox("SOCKS5")
        socks_form = QFormLayout(socks_group)
        self.socks_group = socks_group
        self.socks_host = QLineEdit()
        self.socks_port = self._port_spinbox(1080)
        self.socks_timeout = self._seconds_spinbox(20)
        self.socks_host_label = QLabel()
        self.socks_port_label = QLabel()
        self.socks_timeout_label = QLabel()
        socks_form.addRow(self.socks_host_label, self.socks_host)
        socks_form.addRow(self.socks_port_label, self.socks_port)
        socks_form.addRow(self.socks_timeout_label, self.socks_timeout)
        layout.addWidget(socks_group)

        self.app_group = QGroupBox()
        app_form = QFormLayout(self.app_group)
        self.language_combo = QComboBox()
        self.language_combo.addItem("Auto", LANG_AUTO)
        self.language_combo.addItem("English", LANG_EN)
        self.language_combo.addItem("中文", LANG_ZH)
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        self.log_level = QComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.language_label = QLabel()
        self.log_level_label = QLabel()
        self.start_on_launch_checkbox = QCheckBox()
        self.launch_at_login_checkbox = QCheckBox()
        self.keep_in_menu_bar_checkbox = QCheckBox()
        self.keep_in_menu_bar_checkbox.stateChanged.connect(self._menu_bar_preference_changed)
        app_form.addRow(self.language_label, self.language_combo)
        app_form.addRow(self.log_level_label, self.log_level)
        app_form.addRow(self.start_on_launch_checkbox)
        app_form.addRow(self.launch_at_login_checkbox)
        app_form.addRow(self.keep_in_menu_bar_checkbox)
        layout.addWidget(self.app_group)

        layout.addStretch(1)
        return page

    def _build_runtime_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.status_label = QLabel()
        self.start_button = QPushButton()
        self.start_button.clicked.connect(self.start_gateway)
        self.stop_button = QPushButton()
        self.stop_button.clicked.connect(self.stop_gateway)
        self.stop_button.setEnabled(False)
        self.quit_button = QPushButton()
        self.quit_button.clicked.connect(self.quit_app)
        controls.addWidget(self.status_label, 1)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.quit_button)
        layout.addLayout(controls)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        layout.addWidget(self.log_view, 1)
        return page

    def _build_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        )
        self.tray_icon.activated.connect(self._tray_activated)

        self.tray_menu = QMenu(self)
        self.tray_show_action = QAction(self)
        self.tray_show_action.triggered.connect(self.show_configuration)
        self.tray_start_action = QAction(self)
        self.tray_start_action.triggered.connect(self.start_gateway)
        self.tray_stop_action = QAction(self)
        self.tray_stop_action.triggered.connect(self.stop_gateway)
        self.tray_quit_action = QAction(self)
        self.tray_quit_action.triggered.connect(self.quit_app)

        self.tray_menu.addAction(self.tray_show_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.tray_start_action)
        self.tray_menu.addAction(self.tray_stop_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.tray_quit_action)
        self.tray_icon.setContextMenu(self.tray_menu)

    def load_config(self) -> None:
        try:
            data = load_raw_config(self._config_path)
            self._loading_config = True
            self._apply_to_widgets(data)
            self._loading_config = False
            self._append_log(self.tr("config_loaded"))
        except Exception as exc:
            self._loading_config = False
            self._show_error(self.tr("load_failed"), str(exc))

    def save_config(self) -> None:
        try:
            data = self._collect_from_widgets()
            save_raw_config(self._config_path, data)
            self._apply_launch_agent_state()
            self._append_log(self.tr("config_saved"))
        except Exception as exc:
            self._show_error(self.tr("save_failed"), str(exc))

    def start_gateway(self) -> None:
        if self._gateway_thread is not None and self._gateway_thread.isRunning():
            return
        self.save_config()
        self._gateway_thread = GatewayThread(self._config_path)
        self._gateway_thread.status_changed.connect(self._set_status)
        self._gateway_thread.failed.connect(self._gateway_failed)
        self._gateway_thread.stopped.connect(self._gateway_stopped)
        self._gateway_thread.start()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def stop_gateway(self) -> None:
        if self._gateway_thread is None:
            return
        self._gateway_thread.stop()
        self.status_label.setText(self.tr("stopping_gateway"))
        self._update_tray_actions()

    def generate_certificate(self) -> None:
        try:
            cert_file = self._resolve_path(self.cert_file.text())
            key_file = self._resolve_path(self.key_file.text())
            generate_localhost_cert(cert_file, key_file)
            self._append_log(f"Generated certificate: {cert_file}")
            QMessageBox.information(self, self.tr("certificate"), self.tr("cert_generated"))
        except Exception as exc:
            self._show_error(self.tr("cert_gen_failed"), str(exc))

    def trust_certificate(self) -> None:
        try:
            cert_file = self._resolve_path(self.cert_file.text())
            if not cert_file.exists():
                raise FileNotFoundError(cert_file)
            trust_cert_macos(cert_file)
            self._append_log(f"Trusted certificate: {cert_file}")
            QMessageBox.information(self, self.tr("certificate"), self.tr("cert_trusted"))
        except Exception as exc:
            self._show_error(self.tr("cert_trust_failed"), str(exc))

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._really_quitting and self._should_keep_in_menu_bar():
            event.ignore()
            self.hide()
            self._append_log(self.tr("hidden_to_tray"))
            return

        logging.getLogger().removeHandler(self._log_handler)
        if self._gateway_thread is not None and self._gateway_thread.isRunning():
            self._gateway_thread.stop()
            self._gateway_thread.wait(3000)
        self.tray_icon.hide()
        event.accept()

    def show_initial(self) -> None:
        if self._initial_visibility == "hidden":
            self.hide()
            return
        if self._initial_visibility == "minimized":
            self.showMinimized()
            return
        self.show()

    def show_configuration(self) -> None:
        self.tabs.setCurrentWidget(self.config_tab)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._really_quitting = True
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _apply_to_widgets(self, data: dict[str, Any]) -> None:
        gateway = data["gateway"]
        socks5 = data["socks5"]
        logging_config = data["logging"]
        app = data.get("app", {})

        self.listen_host.setText(str(gateway["listen_host"]))
        self.listen_port.setValue(int(gateway["listen_port"]))
        self.username.setText(str(gateway["username"]))
        self.password.setText(str(gateway["password"]))
        self.cert_file.setText(str(gateway["cert_file"]))
        self.key_file.setText(str(gateway["key_file"]))
        self.read_timeout.setValue(int(float(gateway["read_timeout_seconds"])))

        self.socks_host.setText(str(socks5["host"]))
        self.socks_port.setValue(int(socks5["port"]))
        self.socks_timeout.setValue(int(float(socks5["connect_timeout_seconds"])))

        level = str(logging_config.get("level", "INFO")).upper()
        self.log_level.setCurrentText(level if level in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO")
        language = str(app.get("language", LANG_AUTO))
        self._set_language_combo(language)
        self.start_on_launch_checkbox.setChecked(bool(app.get("start_gateway_on_launch", False)))
        self.launch_at_login_checkbox.setChecked(
            bool(app.get("launch_at_login", False)) or is_launch_agent_installed()
        )
        self.keep_in_menu_bar_checkbox.setChecked(bool(app.get("keep_in_menu_bar", False)))
        self._language = resolve_language(language)
        self._retranslate()
        self._update_tray_visibility()

    def _collect_from_widgets(self) -> dict[str, Any]:
        return {
            "gateway": {
                "listen_host": self.listen_host.text().strip() or "127.0.0.1",
                "listen_port": self.listen_port.value(),
                "username": self.username.text().strip(),
                "password": self.password.text(),
                "cert_file": self.cert_file.text().strip(),
                "key_file": self.key_file.text().strip(),
                "read_timeout_seconds": self.read_timeout.value(),
            },
            "socks5": {
                "host": self.socks_host.text().strip() or "127.0.0.1",
                "port": self.socks_port.value(),
                "connect_timeout_seconds": self.socks_timeout.value(),
            },
            "logging": {
                "level": self.log_level.currentText(),
            },
            "app": {
                "start_gateway_on_launch": self.start_on_launch_checkbox.isChecked(),
                "launch_at_login": self.launch_at_login_checkbox.isChecked(),
                "keep_in_menu_bar": self.keep_in_menu_bar_checkbox.isChecked(),
                "language": self.language_combo.currentData() or LANG_AUTO,
            },
        }

    def _apply_launch_agent_state(self) -> None:
        if self.launch_at_login_checkbox.isChecked():
            install_launch_agent(self._config_path)
            self._append_log(self.tr("launch_enabled"))
        else:
            uninstall_launch_agent()
            self._append_log(self.tr("launch_disabled"))

    def _browse_file(self, target: QLineEdit, title: str) -> None:
        selected, _filter = QFileDialog.getOpenFileName(self, title, str(self._config_path.parent))
        if selected:
            target.setText(selected)

    def _resolve_path(self, value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self._config_path.parent / path
        return path.resolve()

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)
        self._append_log(message)
        self._update_tray_actions()

    def _gateway_failed(self, message: str) -> None:
        self._append_log(f"Gateway failed: {message}")
        self._show_error(self.tr("gateway_failed"), message)

    def _gateway_stopped(self) -> None:
        self.status_label.setText(self.tr("gateway_stopped"))
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._append_log(self.tr("gateway_stopped"))
        self._update_tray_actions()

    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def tr(self, key: str) -> str:
        return TEXT[self._language].get(key, TEXT[LANG_EN].get(key, key))

    def _language_changed(self) -> None:
        if self._loading_config:
            return
        self._language = resolve_language(self.language_combo.currentData())
        self._retranslate()

    def _set_language_combo(self, value: str) -> None:
        self.language_combo.blockSignals(True)
        for index in range(self.language_combo.count()):
            if self.language_combo.itemData(index) == value:
                self.language_combo.setCurrentIndex(index)
                break
        else:
            self.language_combo.setCurrentIndex(0)
        self.language_combo.blockSignals(False)

    def _retranslate(self) -> None:
        current_status = self.status_label.text() if hasattr(self, "status_label") else ""
        self.setWindowTitle(self.tr("window_title"))
        self.tabs.setTabText(0, self.tr("tab_config"))
        self.tabs.setTabText(1, self.tr("tab_runtime"))
        self.save_action.setText(self.tr("save"))
        self.reload_button.setText(self.tr("reload"))
        self.save_button.setText(self.tr("save"))
        self.config_file_label.setText(self.tr("config_file"))
        self.gateway_group.setTitle(self.tr("gateway"))
        self.listen_host_label.setText(self.tr("listen_host"))
        self.listen_port_label.setText(self.tr("listen_port"))
        self.username_label.setText(self.tr("gateway_username"))
        self.password_label.setText(self.tr("gateway_password"))
        self._update_password_toggle_text()
        self.read_timeout_label.setText(self.tr("read_timeout"))
        self.cert_group.setTitle(self.tr("certificate"))
        self.cert_file_label.setText(self.tr("certificate_file"))
        self.key_file_label.setText(self.tr("key_file"))
        self.cert_browse.setText(self.tr("browse"))
        self.key_browse.setText(self.tr("browse"))
        self.generate_button.setText(self.tr("generate_cert"))
        self.trust_button.setText(self.tr("trust_cert"))
        self.socks_group.setTitle("SOCKS5")
        self.socks_host_label.setText(self.tr("socks_host"))
        self.socks_port_label.setText(self.tr("socks_port"))
        self.socks_timeout_label.setText(self.tr("connect_timeout"))
        self.app_group.setTitle(self.tr("app"))
        self.language_label.setText(self.tr("language"))
        self.log_level_label.setText(self.tr("log_level"))
        self.start_on_launch_checkbox.setText(self.tr("start_on_launch"))
        self.launch_at_login_checkbox.setText(self.tr("launch_at_login"))
        self.keep_in_menu_bar_checkbox.setText(self.tr("keep_in_menu_bar"))
        self.start_button.setText(self.tr("start_gateway"))
        self.stop_button.setText(self.tr("stop_gateway"))
        self.quit_button.setText(self.tr("quit_app"))
        if not current_status or current_status in {
            TEXT[LANG_EN]["gateway_stopped"],
            TEXT[LANG_ZH]["gateway_stopped"],
        }:
            self.status_label.setText(self.tr("gateway_stopped"))
        self._retranslate_language_combo()
        self._update_tray_actions()

    def _retranslate_language_combo(self) -> None:
        current = self.language_combo.currentData()
        self.language_combo.blockSignals(True)
        self.language_combo.setItemText(0, self.tr("language_auto"))
        self.language_combo.setItemText(1, self.tr("language_en"))
        self.language_combo.setItemText(2, self.tr("language_zh"))
        for index in range(self.language_combo.count()):
            if self.language_combo.itemData(index) == current:
                self.language_combo.setCurrentIndex(index)
                break
        self.language_combo.blockSignals(False)

    def _menu_bar_preference_changed(self) -> None:
        if self._loading_config:
            return
        self._update_tray_visibility()

    def _should_keep_in_menu_bar(self) -> bool:
        return (
            self.keep_in_menu_bar_checkbox.isChecked()
            and QSystemTrayIcon.isSystemTrayAvailable()
        )

    def _update_tray_visibility(self) -> None:
        app = QApplication.instance()
        keep_enabled = self._should_keep_in_menu_bar()
        if app is not None:
            app.setQuitOnLastWindowClosed(not keep_enabled)

        if keep_enabled:
            if not self.tray_icon.isVisible():
                self.tray_icon.show()
        else:
            self.tray_icon.hide()
            if self.keep_in_menu_bar_checkbox.isChecked():
                self._append_log(self.tr("tray_not_available"))
        self._update_tray_actions()

    def _update_tray_actions(self) -> None:
        running = self._gateway_thread is not None and self._gateway_thread.isRunning()
        self.tray_show_action.setText(self.tr("show_configuration"))
        self.tray_start_action.setText(self.tr("start_gateway"))
        self.tray_stop_action.setText(self.tr("stop_gateway"))
        self.tray_quit_action.setText(self.tr("quit_app"))
        self.tray_start_action.setEnabled(not running)
        self.tray_stop_action.setEnabled(running)
        self.tray_icon.setToolTip(f"RDP Gateway\n{self.status_label.text()}")

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_configuration()

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_visible = checked
        self.password.setEchoMode(
            QLineEdit.EchoMode.Normal
            if self.password_visible
            else QLineEdit.EchoMode.Password
        )
        self._update_password_toggle_text()

    def _update_password_toggle_text(self) -> None:
        self.password_toggle_button.setText(
            self.tr("hide_password")
            if self.password_visible
            else self.tr("show_password")
        )

    @staticmethod
    def _port_spinbox(default: int) -> QSpinBox:
        spinbox = QSpinBox()
        spinbox.setRange(1, 65535)
        spinbox.setValue(default)
        return spinbox

    @staticmethod
    def _seconds_spinbox(default: int) -> QSpinBox:
        spinbox = QSpinBox()
        spinbox.setRange(1, 3600)
        spinbox.setValue(default)
        return spinbox


class SingleInstanceServer(QObject):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._handle_connection)

    def listen(self) -> bool:
        if self._server.listen(SINGLE_INSTANCE_SERVER):
            return True
        QLocalServer.removeServer(SINGLE_INSTANCE_SERVER)
        return self._server.listen(SINGLE_INSTANCE_SERVER)

    def close(self) -> None:
        self._server.close()
        QLocalServer.removeServer(SINGLE_INSTANCE_SERVER)

    def _handle_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            socket.readyRead.connect(
                lambda sock=socket: self._handle_socket_ready(sock)
            )
            socket.disconnected.connect(socket.deleteLater)

    def _handle_socket_ready(self, socket: QLocalSocket) -> None:
        command = bytes(socket.readAll()).strip().lower()
        if command == SINGLE_INSTANCE_SHOW_COMMAND.strip():
            self._window.show_configuration()
        socket.disconnectFromServer()


def notify_existing_instance() -> bool:
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_SERVER)
    if not socket.waitForConnected(250):
        return False

    socket.write(SINGLE_INSTANCE_SHOW_COMMAND)
    socket.flush()
    socket.waitForBytesWritten(250)
    socket.disconnectFromServer()
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RDP Gateway GUI")
    parser.add_argument("--config", default=None, help="Path to config.toml")
    parser.add_argument(
        "--autostart",
        action="store_true",
        help="Start the gateway after launching the GUI.",
    )
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser().resolve() if args.config else default_config_path()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("RDP Gateway")
    if notify_existing_instance():
        return 0

    window = MainWindow(config_path, autostart=args.autostart)
    single_instance = SingleInstanceServer(window)
    single_instance.listen()
    app.aboutToQuit.connect(single_instance.close)
    window.show_initial()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
