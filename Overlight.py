import os
import sys
import time
import json
import ctypes
import psutil
import base64
import iconbase
import threading
from PIL import Image
from io import BytesIO
from ctypes import wintypes
from PyQt5.QtCore import Qt, QEvent, QObject
from PyQt5.QtGui import QIcon, QPixmap, QImage, QCursor
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QWidget, QVBoxLayout, QSlider, QFrame

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
shcore = ctypes.windll.shcore if hasattr(ctypes.windll, "shcore") else None
WM_HOTKEY = 0x0312
VK_UP = 0x26
VK_DOWN = 0x28
VK_ESCAPE = 0x1B
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
ICON_BASE64_DATA = iconbase.icon_base
_current_opacity = 50
_step_percent = 5
_tray_icon = None
_slider = None
_slider_root = None
_slider_widget = None
_running = True
CONFIG_DIR = "data"
CONFIG_FILE = "config.json"
DEFAULT_OPACITY = 50
CONFIG_PATH = os.path.join(CONFIG_DIR, CONFIG_FILE)

def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            opacity = int(config.get('opacity_percent', DEFAULT_OPACITY))
            opacity = max(0, min(50, opacity))
            return opacity
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_OPACITY
    except Exception as e:
        return DEFAULT_OPACITY

def save_config():
    global _current_opacity

    config = {'opacity_percent': _current_opacity}

    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        return
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        pass

def set_dpi_awareness():
    try:
        shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

def set_low_priority():
    try:
        p = psutil.Process(os.getpid())
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except:
        pass

def update_opacity(change):
    global _current_opacity, _tray_icon, _slider

    _current_opacity = max(0, min(50, _current_opacity + change))
    set_gamma_brightness(_current_opacity)
    brightness_percent = 100 - _current_opacity
    msg = f"Overlight: {brightness_percent}%"

    if _tray_icon:
        _tray_icon.setToolTip(msg)
    if _slider and _slider_widget and _slider_widget.isVisible():
        _slider.setValue(brightness_percent)

def set_gamma_brightness(opacity_percent):
    level = max(0.5, (100 - opacity_percent) / 100.0)
    hdc = user32.GetDC(None)
    ramp = (wintypes.WORD * 768)()
    for i in range(256):
        val = int(i * level * 257)
        if val > 65535:
            val = 65535

        ramp[i] = ramp[i+256] = ramp[i+512] = val
    gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp))
    user32.ReleaseDC(None, hdc)

def reset_gamma_ramp():
    try:
        hdc = user32.GetDC(None)
        ramp = (wintypes.WORD * 768)()
        for i in range(256):
            val = int(i * 257)
            if val > 65535:
                val = 65535

            ramp[i] = ramp[i + 256] = ramp[i + 512] = val
        gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp))
        user32.ReleaseDC(None, hdc)
    except:
        pass

def make_overlay(initial_percent, step_percent):
    global _current_opacity, _step_percent

    _current_opacity = initial_percent
    _step_percent = step_percent
    modifiers = MOD_CONTROL | MOD_ALT
    user32.RegisterHotKey(None, 1, modifiers, VK_UP)
    user32.RegisterHotKey(None, 2, modifiers, VK_DOWN)
    user32.RegisterHotKey(None, 3, modifiers, VK_ESCAPE)
    update_opacity(0)
    set_gamma_brightness(_current_opacity)
    msg = wintypes.MSG()
    last_check_time = time.time()

    try:
        while _running:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == WM_HOTKEY:
                    kid = int(msg.wParam)
                    if kid == 1:
                        update_opacity(-_step_percent)
                    elif kid == 2:
                        update_opacity(_step_percent)
                    elif kid == 3:
                        break

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            current_time = time.time()
            if current_time - last_check_time > 2.0:
                set_gamma_brightness(_current_opacity)
                last_check_time = current_time

            time.sleep(0.1)

    finally:
        save_config()
        user32.UnregisterHotKey(None, 1)
        user32.UnregisterHotKey(None, 2)
        user32.UnregisterHotKey(None, 3)
        reset_gamma_ramp()

def show_slider():
    global _slider_widget, _current_opacity, _slider
    if _slider_widget:
        if _slider:
            brightness_percent = 100 - _current_opacity
            _slider.setValue(brightness_percent)
        cursor_pos = QCursor.pos()
        _slider_widget.move(cursor_pos.x() - 100, cursor_pos.y() - 50)
        _slider_widget.show()
        _slider_widget.raise_()
        _slider_widget.activateWindow()

def hide_slider():
    global _slider_widget
    if _slider_widget:
        _slider_widget.hide()

def update_from_slider(value):
    global _current_opacity
    _current_opacity = 100 - value
    update_opacity(0)

def run_tray_icon():
    global _tray_icon, _slider_widget, _running, _slider

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dark_style = """
        /* Colores oscuros globales */
        QWidget {
            background-color: #2e2e2e; /* Fondo gris oscuro por defecto */
            color: #ffffff; /* Texto blanco */
            border-radius: 8px;
        }

        /* Estilo para el QFrame (contenedor del slider con fondo gris redondeado) */
        QFrame {
            background-color: #2e2e2e; /* Fondo gris oscuro */
            border-radius: 4px; /* Bordes redondeados */
        }

        /* Estilo del QSlider */
        QSlider::groove:horizontal {
            border: 0px solid #4f4f4f;
            height: 8px; /* Altura de la ranura */
            background: #4f4f4f;
            margin: 0px 0;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #8215b0; /* Color del tirador (violeta) */
            border: 1px solid #711a96;
            width: 12px;
            margin: -3px 0;
            border-radius: 7px;
        }
        QSlider::sub-page:horizontal {
            background: #8215b0;
            border-radius: 3px;
        }

        /* Estilo del QMenu (para el icono de la bandeja) */
        QMenu {
            background-color: #2e2e2e; /* Fondo más oscuro para el menú */
            color: #ffffff;
            border: 1px solid #3a3a3a;
            border-radius: 0px;
        }
        QMenu::item {
            padding: 4px 25px 4px 10px;
            background-color: transparent;
        }
        QMenu::item:selected { 
            background-color: #8215b0; /* Color de resaltado */
        }
        QMenu::separator {
            height: 1px;
            background: #3a3a3a;
            margin: 4px 10px;
        }
        """
    app.setStyleSheet(dark_style)

    _slider_widget = QWidget()
    _slider_widget.setAttribute(Qt.WA_TranslucentBackground)
    _slider_widget.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    _slider_widget.setFixedSize(200, 40)
    frame = QFrame(_slider_widget)
    frame.setGeometry(0, 4, 200, 32)
    layout = QVBoxLayout()
    layout.setContentsMargins(5, 0, 5, 0)
    _slider = QSlider(Qt.Horizontal)
    _slider.setRange(50, 100)
    _slider.setValue(100 - _current_opacity)
    _slider.valueChanged.connect(update_from_slider)
    layout.addWidget(_slider)
    _slider_widget.setLayout(layout)
    _slider_widget.hide()

    class EventFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.MouseButtonPress and _slider_widget.isVisible():
                widget_under_cursor = app.widgetAt(event.globalPos())
                if widget_under_cursor is None or not _slider_widget.isAncestorOf(widget_under_cursor):
                    hide_slider()
            return False
    event_filter = EventFilter()
    app.installEventFilter(event_filter)

    def on_focus_changed(old_widget, new_widget):
        if _slider_widget.isVisible() and (new_widget is None or not _slider_widget.isAncestorOf(new_widget)):
            hide_slider()

    app.focusChanged.connect(on_focus_changed)

    try:
        icon_data = base64.b64decode(ICON_BASE64_DATA)
        icon_image = Image.open(BytesIO(icon_data))
        icon_image = icon_image.convert("RGBA")
        data = icon_image.tobytes("raw", "RGBA")
        qimage = QImage(data, icon_image.size[0], icon_image.size[1], QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)
        icon = QIcon(pixmap)
    except:
        qimage_fallback = QImage(64, 64, QImage.Format_RGB32)
        qimage_fallback.fill(Qt.black)
        icon = QIcon(QPixmap.fromImage(qimage_fallback))

    initial_brightness = 100 - _current_opacity
    _tray_icon = QSystemTrayIcon(icon)
    _tray_icon.setToolTip(f"Overlight: {initial_brightness}%")

    menu = QMenu()
    increase_action = QAction("Increase Brightness", menu)
    increase_action.triggered.connect(lambda: update_opacity(-_step_percent))
    menu.addAction(increase_action)

    decrease_action = QAction("Decrease Brightness", menu)
    decrease_action.triggered.connect(lambda: update_opacity(_step_percent))
    menu.addAction(decrease_action)

    menu.addSeparator()

    def exit_app():
        global _running
        _running = False
        hide_slider()
        reset_gamma_ramp()
        time.sleep(0.5)
        app.quit()

    exit_action = QAction("Exit", menu)
    exit_action.triggered.connect(exit_app)
    menu.addAction(exit_action)
    _tray_icon.setContextMenu(menu)
    _tray_icon.activated.connect(lambda reason: show_slider() if reason == QSystemTrayIcon.Trigger else None)
    _tray_icon.show()

    app.exec_()

if __name__ == "__main__":
    set_dpi_awareness()
    set_low_priority()
    initial_opacity = load_config()
    step = 5
    overlay_thread = threading.Thread(target=make_overlay, args=(initial_opacity, step))
    overlay_thread.daemon = True

    try:
        overlay_thread.start()
        time.sleep(1)
        run_tray_icon()
    except Exception as e:
        sys.exit(1)
