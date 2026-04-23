"""
CRAVE Phase 12 — Custom Audio Wave UI
Save to: D:\\CRAVE\\src\\ui\\orb.py

Provides a multi-bar frequency EQ visualizer just like FRIDAY, replacing the orb.
Has functional close, minimize, and mic buttons.
"""

import os
import sys
import json
import math
import time
import threading
import psutil
from pathlib import Path
from PyQt6.QtWidgets import QInputDialog, QMessageBox

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QLineEdit, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect,
    QSizePolicy, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint,
    QRect, pyqtSignal, pyqtSlot, QSize, QSettings
)
from PyQt6.QtGui import (
    QPainter, QColor, QRadialGradient, QBrush, QPen, QFont,
    QFontDatabase, QKeySequence, QShortcut, QIcon, QPixmap,
    QLinearGradient, QPainterPath, QAction
)

ORB_STATES = {
    "idle":      {"color1": "#0055FF", "color2": "#002288", "label": "READY"},
    "listening": {"color1": "#00FFEE", "color2": "#008B8B", "label": "LISTENING"},
    "thinking":  {"color1": "#FFD700", "color2": "#B8860B", "label": "THINKING"},
    "speaking":  {"color1": "#00E5FF", "color2": "#0055FF", "label": "SPEAKING"},  # Friday Blue
    "error":     {"color1": "#FF3131", "color2": "#8B0000", "label": "ERROR"},
    "lockdown":  {"color1": "#FF0000", "color2": "#440000", "label": "LOCKDOWN"},
    "silent":    {"color1": "#616161", "color2": "#2C2C2C", "label": "SILENT"},
}

SETTINGS_FILE = os.path.join(
    os.environ.get("CRAVE_ROOT", "D:\\CRAVE"), "config", "orb_settings.json"
)

# ── Dynamic Audio Wave Widget ────────────────────────────────────────────────

class WaveWidget(QWidget):
    """The glowing animated multi-bar frequency wave."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 80)
        self._state = "idle"
        self._bars = [0.2] * 7  # 7 equalizer bars
        self._target_bars = [0.2] * 7
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)  # 25fps

    def set_state(self, state: str):
        if state in ORB_STATES:
            self._state = state

    def _tick(self):
        import random
        # Determine target heights based on state
        for i in range(len(self._target_bars)):
            if self._state == "speaking":
                # Wild high frequency movement
                self._target_bars[i] = random.uniform(0.3, 1.0)
            elif self._state == "thinking":
                # Staggered wave processing effect
                phase = (time.time() * 5 + i) % 7
                self._target_bars[i] = 0.5 + 0.3 * math.sin(phase)
            elif self._state == "listening":
                # Minimal active bounce
                self._target_bars[i] = random.uniform(0.2, 0.45)
            else:
                # Flatline or very low
                self._target_bars[i] = 0.15 + (math.sin(time.time() * 2 + i) * 0.05)

        # Smoothly interpolate current bars to target
        for i in range(len(self._bars)):
            diff = self._target_bars[i] - self._bars[i]
            # Speed of smoothing
            self._bars[i] += diff * 0.3
            
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        state_info = ORB_STATES.get(self._state, ORB_STATES["idle"])
        base_color = QColor(state_info["color1"])
        
        bar_w = 14
        spacing = 10
        total_width = (len(self._bars) * bar_w) + ((len(self._bars) - 1) * spacing)
        start_x = (w - total_width) / 2
        cy = h / 2

        # Draw Glow Behind
        if self._state in ["speaking", "listening", "thinking"]:
            glow_grad = QRadialGradient(w/2, h/2, w/2)
            gc = QColor(base_color)
            gc.setAlpha(40)
            glow_grad.setColorAt(0.0, gc)
            gc.setAlpha(0)
            glow_grad.setColorAt(1.0, gc)
            painter.setBrush(QBrush(glow_grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, -20, w, h+40)

        # Draw Bars
        for i, val in enumerate(self._bars):
            bar_h = h * val * 0.8
            # Minimum height
            bar_h = max(bar_h, 8)
            
            x = start_x + (i * (bar_w + spacing))
            y = cy - (bar_h / 2)
            
            # Gradient for each bar
            grad = QLinearGradient(x, y, x, y + bar_h)
            c1 = QColor(base_color)
            c2 = QColor(state_info["color2"])
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(x), int(y), bar_w, int(bar_h), 6, 6)

        painter.end()


# ── Terminal Widget (Replaces Live Captions) ──────────────────────────────────

class TerminalWidget(QWidget):
    dismiss_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(180)
        self.setMinimumWidth(400)

        self.setStyleSheet("""
            TerminalWidget {
                background: transparent;
                border: none;
                border-radius: 0px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header for stats
        self._header = QLabel("SYSTEM: ONLINE | CPU: 0% | RAM: 0% | CONTEXT: 0")
        self._header.setStyleSheet("color: #00FFCC; font-family: 'Consolas'; font-size: 11px; font-weight: bold; background: transparent; border: none; letter-spacing: 1px;")
        layout.addWidget(self._header)

        # Divider line
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: rgba(0, 255, 204, 0.3);")
        layout.addWidget(divider)

        from PyQt6.QtWidgets import QTextBrowser
        self._term = QTextBrowser()
        self._term.setStyleSheet("""
            QTextBrowser {
                color: #BBE1FA; 
                font-family: 'Consolas', 'Courier New', monospace; 
                font-size: 13px; 
                background: transparent; 
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(0,0,0,0);
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 255, 204, 0.4);
                border-radius: 3px;
            }
        """)
        self._term.setOpenExternalLinks(True)
        self._term.setHtml('<div style="color: #00FFCC; font-weight: bold;">[SYSTEM INITIALIZED] Monitoring Active...</div>')
        layout.addWidget(self._term)

        # Stats Timer
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(2000)

    def _update_stats(self):
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            
            # Get orchestrator context length
            ctx = 0
            from src.core.orchestrator import _global_orchestrator
            if _global_orchestrator:
                ctx = len(_global_orchestrator._context)
                
            self._header.setText(f"CPU: {cpu}% | RAM: {ram}% | CONTEXT: {ctx}/50")
        except:
            pass

    def set_user_text(self, text: str):
        # Add to terminal
        display = f'<div style="color: #00E5FF; margin-bottom: 4px;">&gt; {text}</div>'
        self._term.append(display)

    def set_reply_text(self, text: str):
        # Simple markdown-like to HTML conversion for bold/italics
        import re
        html = text.replace('\\n', '<br>').replace('\n', '<br>')
        html = re.sub(r'\\*\\*(.*?)\\*\\*', r'<b>\1</b>', html)
        html = re.sub(r'_(.*?)_', r'<i>\1</i>', html)
        # Wrap images if there are HTTP links ending in png/jpg
        html = re.sub(r'(https?://\\S+\\.(?:png|jpg|jpeg|gif))', r'<br><img src="\\1" width="200" /><br>', html)
        
        display = f'<div style="color: rgba(255, 255, 255, 0.9); margin-bottom: 8px;">{html}</div>'
        self._term.append(display)

    def clear(self):
        self._term.clear()
        self._term.setHtml("<div>System cleared.</div>")
        
    def paintEvent(self, event):
        from PyQt6.QtWidgets import QStyleOption, QStyle
        from PyQt6.QtGui import QPainter
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self)


class SilentInputWidget(QWidget):
    command_submitted = pyqtSignal(str)
    auth_failed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._cmd_input = QLineEdit()
        self._cmd_input.setPlaceholderText("Type command...")
        self._cmd_input.setStyleSheet("""
            QLineEdit {
                background: rgba(10, 15, 25, 200);
                color: #FFFFFF;
                border: 1px solid rgba(0, 229, 255, 0.6);
                border-radius: 6px; padding: 10px; font-size: 14px;
            }
        """)
        self._cmd_input.returnPressed.connect(self._submit)
        layout.addWidget(self._cmd_input)

    def _submit(self):
        t = self._cmd_input.text().strip()
        if t:
            self.command_submitted.emit(t)
            self._cmd_input.clear()
            
    def focus_input(self):
        self._cmd_input.setFocus()
        
    def reset(self):
        self._cmd_input.clear()


# ── Main FRIDAY UI Window ────────────────────────────────────────────────────

class CRAVEOrb(QMainWindow):
    sig_state          = pyqtSignal(str)
    sig_user_command   = pyqtSignal(str)
    sig_crave_reply    = pyqtSignal(str)
    sig_show_bar       = pyqtSignal()
    sig_toggle_silent  = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("FRIDAY")

        self._silent_mode = False
        self._bar_visible = True
        self._dragging = False
        self._drag_offset = QPoint()
        self._orchestrator = None

        central = QWidget()
        central.setObjectName("CentralBox")
        central.setStyleSheet("""
            #CentralBox {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(10, 15, 30, 245), stop:1 rgba(2, 5, 10, 245));
                border: 1px solid rgba(0, 255, 204, 0.6);
                border-radius: 12px;
            }
        """)

        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        from PyQt6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect(central)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 255, 204, 90))
        shadow.setOffset(0, 0)
        central.setGraphicsEffect(shadow)

        self.setCentralWidget(central)
        self._main_layout = QVBoxLayout(central)
        self._main_layout.setContentsMargins(10, 10, 10, 10)
        self._main_layout.setSpacing(8)
        self._main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Top Control Bar (Mic, Minimize, Close)
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0,0,0,0)
        ctrl_layout.addStretch()
        
        btn_style = """
            QPushButton { background: rgba(10, 15, 25, 180); color: #00E5FF; border: 1px solid rgba(0, 229, 255, 0.3); border-radius: 12px; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background: rgba(0, 229, 255, 0.2); }
        """
        btn_style_close = """
            QPushButton { background: rgba(10, 15, 25, 180); color: #FF5252; border: 1px solid rgba(255, 82, 82, 0.3); border-radius: 12px; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background: rgba(255, 82, 82, 0.2); }
        """

        self._mic_btn = QPushButton("🎙")
        self._mic_btn.setFixedSize(24, 24)
        self._mic_btn.setStyleSheet(btn_style)
        self._mic_btn.clicked.connect(self.toggle_silent)
        
        self._min_btn = QPushButton("—")
        self._min_btn.setFixedSize(24, 24)
        self._min_btn.setStyleSheet(btn_style)
        self._min_btn.clicked.connect(self.hide)
        
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setStyleSheet(btn_style_close)
        self._close_btn.clicked.connect(self.close)

        ctrl_layout.addWidget(self._mic_btn)
        ctrl_layout.addWidget(self._min_btn)
        ctrl_layout.addWidget(self._close_btn)
        self._main_layout.addLayout(ctrl_layout)

        # Visualizer Wave
        self._wave = WaveWidget()
        self._main_layout.addWidget(self._wave, alignment=Qt.AlignmentFlag.AlignCenter)

        # Status Label
        self._state_label = QLabel("READY")
        self._state_label.setStyleSheet("color: #00E5FF; font-family: 'Consolas'; font-size: 10px; font-weight: bold; letter-spacing: 2px;")
        self._state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(self._state_label)

        self._setup_system_tray()

        self._status_bar = TerminalWidget()
        self._status_bar.dismiss_clicked.connect(self.dismiss_bar)
        self._main_layout.addWidget(self._status_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        self._silent_input = SilentInputWidget()
        self._silent_input.command_submitted.connect(self._on_text_command)
        self._silent_input.hide()
        self._main_layout.addWidget(self._silent_input, alignment=Qt.AlignmentFlag.AlignCenter)

        self.sig_toggle_silent.connect(self.toggle_silent)
        try:
            import keyboard
            keyboard.add_hotkey('ctrl+shift+j', lambda: self.sig_toggle_silent.emit())
        except:
            self._silent_shortcut = QShortcut(QKeySequence("Ctrl+Shift+J"), self)
            self._silent_shortcut.activated.connect(self.toggle_silent)

        self.sig_state.connect(self._on_set_state)
        self.sig_user_command.connect(self._on_user_command)
        self.sig_crave_reply.connect(self._on_crave_reply)
        self.sig_show_bar.connect(self._on_show_bar)

        self._load_position()
        self.adjustSize()

    def _setup_system_tray(self):
        self._tray_icon = QSystemTrayIcon(self)
        from PyQt6.QtWidgets import QStyle
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self._tray_icon.setIcon(icon)
        tray_menu = QMenu()
        tray_menu.addAction("Restore", self.showNormal)
        tray_menu.addAction("Quit", self.close)
        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _on_tray_activated(self, reason):
        from PyQt6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.activateWindow()

    @pyqtSlot(str)
    def _on_set_state(self, state: str):
        self._wave.set_state(state)
        if state in ORB_STATES:
            info = ORB_STATES[state]
            self._state_label.setText(info["label"])
            self._state_label.setStyleSheet(f"color: {info['color1']}; font-family: 'Consolas'; font-size: 10px; font-weight: bold; letter-spacing: 2px;")

    @pyqtSlot(str)
    def _on_user_command(self, text: str):
        self._status_bar.set_user_text(text)
        self._on_show_bar()

    @pyqtSlot(str)
    def _on_crave_reply(self, text: str):
        self._status_bar.set_reply_text(text)
        self._on_show_bar()

    @pyqtSlot()
    def _on_show_bar(self):
        if not self._silent_mode:
            self._bar_visible = True
            self._status_bar.show()
            self.adjustSize()

    def dismiss_bar(self):
        self._bar_visible = False
        self._status_bar.clear()
        self._status_bar.hide()
        self.adjustSize()

    def toggle_silent(self):
        if not self._silent_mode:
            # We are entering silent mode. Check L2.
            from src.security.rbac import get_rbac
            rbac = get_rbac()
            if rbac.auth_level < 2:
                # Ask for L2 Pin if FaceID hasn't verified
                pin, ok = QInputDialog.getText(self, "L2 Authentication Required", 
                                             "Face ID not verified. Enter L2 PIN to engage silent mode:", 
                                             QLineEdit.EchoMode.Password)
                if not ok or not pin:
                    return
                if not rbac._verify_secret(pin, rbac.credentials.get("L2_PIN_HASH", "")):
                    QMessageBox.warning(self, "Denied", "Incorrect L2 PIN.")
                    return
                rbac.auth_level = max(rbac.auth_level, 2)
                rbac.touch()

            self._silent_mode = True
            # Keep terminal visible entirely instead of hiding it
            # self._status_bar.hide()  <- REMOVED SO TERMINAL STAYS
            self._silent_input.reset()
            self._silent_input.show()
            self._silent_input.focus_input()
            self._on_set_state("silent")
            self._mic_btn.setStyleSheet("QPushButton { background: rgba(255, 82, 82, 0.4); color: white; border-radius: 12px; }")
            if self._orchestrator:
                self._orchestrator.set_silent_mode(True)
        else:
            self._silent_mode = False
            self._silent_input.hide()
            if self._bar_visible:
                self._status_bar.show()
            self._on_set_state("idle")
            self._mic_btn.setStyleSheet("QPushButton { background: rgba(10, 15, 25, 180); color: #00E5FF; border: 1px solid rgba(0, 229, 255, 0.3); border-radius: 12px; }")
            if self._orchestrator:
                self._orchestrator.set_silent_mode(False)
        self.adjustSize()

    def _on_text_command(self, text: str):
        threading.Thread(target=self._handle_cmd_bg, args=(text,), daemon=True).start()

    def _handle_cmd_bg(self, text: str):
        if self._orchestrator:
            # We don't emit user_command or crave_reply here because 
            # orchestrator.handle() already triggers the callbacks.
            try:
                self._orchestrator.handle(text, source="local")
                self.sig_state.emit("speaking")
                time.sleep(2)  # Simulate talk time
            except:
                pass
            self.sig_state.emit("silent" if self._silent_mode else "idle")

    # ── Thread-safe Public API ───────────────────────────────────────────────
    def set_state(self, state: str):
        self.sig_state.emit(state)

    def show_user_command(self, text: str):
        self.sig_user_command.emit(text)

    def show_crave_reply(self, text: str):
        self.sig_crave_reply.emit(text)

    def show_bar(self):
        self.sig_show_bar.emit()

    def set_orchestrator(self, orchestrator):
        self._orchestrator = orchestrator

    # ── Drag & Save Position ─────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._save_position()
            event.accept()

    def closeEvent(self, event):
        self._save_position()
        if self._orchestrator:
            self._orchestrator.stop()
        if hasattr(self, '_tray_icon') and self._tray_icon:
            self._tray_icon.hide()
        event.accept()
        QApplication.quit()

    def _save_position(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump({"x": self.x(), "y": self.y()}, f)
        except Exception as e:
            print(f"[Orb] Save pos failed: {e}")

    def _load_position(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    self.move(data["x"], data["y"])
                return
            except:
                pass
        # Default positioning if no save
        screen_geo = QApplication.primaryScreen().availableGeometry()
        self.move(screen_geo.width() - self.width() - 50, screen_geo.height() - self.height() - 50)

# Orchestrator lifecycle is managed by main.py → orchestrator.get_orchestrator()
# UI stats access uses: from src.core.orchestrator import _global_orchestrator

