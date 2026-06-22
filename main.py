import sys
import random
import ctypes
import ctypes.wintypes
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QWidget
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect, QObject, QEvent
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPainterPath, QPen, QFontMetrics, QCursor
import pyautogui

pyautogui.FAILSAFE = False

IDLE_QUIPS  = ["I'm bored…", "*yawns*", "What's up?", "Pet me! 🐾", "I'm watching you 👀", "*stretches*", "Hello there!"]
FEED_QUIPS  = ["Yum! 😋", "More please!", "So tasty! 🍖", "Nom nom nom~"]
DRINK_QUIPS = ["Ahh, refreshing! 💧", "So cold~", "Glug glug glug 💦"]
SLEEP_QUIPS = ["Night night 💤", "ZZZ…", "Don't disturb me!", "Dreaming… 💭"]
REST_QUIPS  = ["Taking a little break~", "Phew!", "*catches breath*", "Resting my paws 🐾"]
AUTOFEED_QUIPS  = ["Sneaking a snack… 🍖", "Self-service time! 😋", "Gotta feed myself!", "Found some leftovers~"]
AUTODRINK_QUIPS = ["Grabbed some water! 💧", "Self-hydrating~ 💦", "Sipping quietly…", "Refilling myself!"]

WALK_DURATION_MS  = 4000
REST_DURATION_MS  = 5000
STEP_PX           = 3
PHYSICS_MS        = 16
STAT_DRAIN_MS     = 6000
SLEEP_RESTORE_MS  = 4000
QUIP_MS           = 10000

AFK_CHECK_MS      = 1000
AFK_THRESHOLD_MS  = 10000
BUSY_THRESHOLD_MS = 1000
CORNER_MARGIN     = 12
CORNER_STEP_PX    = 6

AUTOFEED_THRESHOLD  = 0.15
AUTODRINK_THRESHOLD = 0.15
AUTOFEED_AMOUNT     = 0.50
AUTODRINK_AMOUNT    = 0.50

EAT_SPRITE_DURATION_MS = 2400

def find_chrome_close_button():
    user32 = ctypes.windll.user32
    hwnd   = None

    def enum_cb(h, _):
        nonlocal hwnd
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf, 256)
        if "Google Chrome" in buf.value and user32.IsWindowVisible(h):
            hwnd = h
            return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    if not hwnd:
        return None
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return QPoint(rect.right - 20, rect.top + 16)

class SpeechBubble(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._text = ""
        self._padding = 12
        self._tail_h  = 14
        self._w = self._h = 0
        self._hide = QTimer(self)
        self._hide.setSingleShot(True)
        self._hide.timeout.connect(self.hide)

    def say(self, text: str, anchor: QPoint, duration_ms: int = 2500):
        self._text = text
        fm      = QFontMetrics(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self._w = fm.horizontalAdvance(text) + self._padding * 2
        self._h = fm.height() + self._padding * 2 + self._tail_h
        self._reposition(anchor)
        self.update()
        self.show()
        self._hide.start(duration_ms)

    def move_to(self, anchor: QPoint):
        if self.isVisible():
            self._reposition(anchor)

    def _reposition(self, anchor: QPoint):
        self.setGeometry(anchor.x() - self._w // 2, anchor.y() - self._h - 4, self._w, self._h)

    def paintEvent(self, _):
        p   = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bh   = h - self._tail_h
        tcx  = w // 2
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, bh, 10, 10)
        path.moveTo(tcx - 8, bh)
        path.lineTo(tcx + 8, bh)
        path.lineTo(tcx, h)
        path.closeSubpath()
        p.setPen(QPen(QColor(180, 180, 200), 1.5))
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawPath(path)
        p.setPen(QColor(50, 50, 70))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        p.drawText(QRect(0, 0, w, bh), Qt.AlignmentFlag.AlignCenter, self._text)

class StatsPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(140, 84)
        self._hunger = self._thirst = self._sleep = 1.0

    def set_stats(self, hunger: float, thirst: float, sleep: float):
        self._hunger = max(0.0, min(1.0, hunger))
        self._thirst = max(0.0, min(1.0, thirst))
        self._sleep  = max(0.0, min(1.0, sleep))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(20, 20, 35, 210))
        p.setPen(QPen(QColor(80, 80, 120, 180), 1))
        p.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)

        rows = [
            ("🍖 Hunger", self._hunger, QColor(255, 120, 80),  QColor(200, 60,  40)),
            ("💧 Thirst",  self._thirst, QColor(80,  180, 255), QColor(40,  100, 200)),
            ("💤 Sleep",   self._sleep,  QColor(160, 100, 255), QColor(100, 50,  180)),
        ]
        lf = QFont("Segoe UI", 7, QFont.Weight.Bold)
        bar_x, bar_w, bar_h = 8, self.width() - 16, 7

        for i, (label, value, full_col, low_col) in enumerate(rows):
            by = 10 + i * 25
            p.setFont(lf)
            p.setPen(QColor(200, 200, 220))
            p.drawText(bar_x, by, 80,    12, Qt.AlignmentFlag.AlignLeft,  label)
            p.drawText(bar_x, by, bar_w, 12, Qt.AlignmentFlag.AlignRight, f"{int(value*100)}%")
            p.setBrush(QColor(50, 50, 70))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bar_x, by + 14, bar_w, bar_h, 3, 3)
            p.setBrush(full_col if value > 0.35 else low_col)
            p.drawRoundedRect(bar_x, by + 14, max(4, int(bar_w * value)), bar_h, 3, 3)


class InfoPanel(QWidget):
    # Close button rect (top-right corner)
    CLOSE_BTN = QRect(230, 8, 22, 22)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(260, 310)

        self._hunger = 1.0
        self._thirst = 1.0
        self._sleep  = 1.0
        self._state_label  = "Idle"
        self._activity     = "AFK"
        self._is_sleeping  = False
        self._is_eating    = False
        self._is_busy      = False
        self._close_hovered = False

        # Global click filter to dismiss when clicking outside
        self._click_filter = _ClickOutsideFilter(self)
        QApplication.instance().installEventFilter(self._click_filter)

    def update_data(self, hunger, thirst, sleep, state_label, activity, is_sleeping, is_eating, is_busy):
        self._hunger       = max(0.0, min(1.0, hunger))
        self._thirst       = max(0.0, min(1.0, thirst))
        self._sleep        = max(0.0, min(1.0, sleep))
        self._state_label  = state_label
        self._activity     = activity
        self._is_sleeping  = is_sleeping
        self._is_eating    = is_eating
        self._is_busy      = is_busy
        self.update()

    def show_at(self, pos: QPoint):
        sr = QApplication.primaryScreen().availableGeometry()
        x  = pos.x()
        y  = pos.y()
        if x + self.width()  > sr.width():
            x = sr.width()  - self.width()  - 8
        if y + self.height() > sr.height():
            y = sr.height() - self.height() - 8
        self.move(x, y)
        self.show()
        self.raise_()

    # ── mouse events for close button ──────────────────────────────────────
    def mouseMoveEvent(self, event):
        hovered = self.CLOSE_BTN.contains(event.position().toPoint())
        if hovered != self._close_hovered:
            self._close_hovered = hovered
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.CLOSE_BTN.contains(event.position().toPoint()):
                self.hide()

    def leaveEvent(self, event):
        if self._close_hovered:
            self._close_hovered = False
            self.update()

    # ── painting ────────────────────────────────────────────────────────────
    def _status_dot_color(self, value):
        if value > 0.60:
            return QColor(80, 220, 120)
        elif value > 0.30:
            return QColor(255, 200, 60)
        else:
            return QColor(255, 80, 80)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.setBrush(QColor(18, 18, 32, 245))
        p.setPen(QPen(QColor(90, 90, 140, 200), 1.5))
        p.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)

        W = self.width()
        pad = 16

        # ── Close button ────────────────────────────────────────────────────
        btn = self.CLOSE_BTN
        btn_bg = QColor(180, 60, 60, 200) if self._close_hovered else QColor(80, 80, 110, 160)
        p.setBrush(btn_bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(btn, 5, 5)
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.setPen(QColor(220, 220, 240))
        p.drawText(btn, Qt.AlignmentFlag.AlignCenter, "✕")

        # Title
        p.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        p.setPen(QColor(240, 240, 255))
        p.drawText(QRect(pad, 14, W - pad * 2 - 30, 24), Qt.AlignmentFlag.AlignLeft, "🐾  Nino")

        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(130, 130, 170))
        p.drawText(QRect(pad, 38, W - pad * 2, 16), Qt.AlignmentFlag.AlignLeft, "Desktop Companion")

        p.setPen(QPen(QColor(60, 60, 100), 1))
        p.drawLine(pad, 60, W - pad, 60)

        # Current state
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QColor(160, 160, 200))
        p.drawText(QRect(pad, 70, W - pad * 2, 14), Qt.AlignmentFlag.AlignLeft, "CURRENT STATE")

        state_colors = {
            "Sleeping": (QColor(100, 60, 200),  QColor(200, 160, 255)),
            "Eating":   (QColor(200, 90, 40),   QColor(255, 180, 120)),
            "Drinking": (QColor(30, 100, 200),  QColor(120, 190, 255)),
            "Hiding":   (QColor(60, 60, 90),    QColor(160, 160, 200)),
            "Roaming":  (QColor(40, 140, 80),   QColor(120, 220, 160)),
            "Resting":  (QColor(100, 80, 40),   QColor(210, 180, 120)),
            "Idle":     (QColor(60, 60, 100),   QColor(160, 160, 200)),
        }
        bg_col, fg_col = state_colors.get(self._state_label, (QColor(50, 50, 80), QColor(180, 180, 220)))

        badge_rect = QRect(pad, 88, W - pad * 2, 28)
        p.setBrush(bg_col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(badge_rect, 8, 8)
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.setPen(fg_col)
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._state_label)

        # User activity
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QColor(160, 160, 200))
        p.drawText(QRect(pad, 126, 80, 14), Qt.AlignmentFlag.AlignLeft, "USER")

        act_col = QColor(255, 120, 80) if self._is_busy else QColor(80, 200, 140)
        act_lbl = "Working 🖥️" if self._is_busy else "Away ☕"
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.setPen(act_col)
        p.drawText(QRect(W // 2, 126, W // 2 - pad, 14), Qt.AlignmentFlag.AlignRight, act_lbl)

        p.setPen(QPen(QColor(60, 60, 100), 1))
        p.drawLine(pad, 146, W - pad, 146)

        # Stats
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QColor(160, 160, 200))
        p.drawText(QRect(pad, 154, W - pad * 2, 14), Qt.AlignmentFlag.AlignLeft, "STATS")

        stats = [
            ("🍖", "Hunger", self._hunger, QColor(255, 140, 80),  QColor(220, 60, 40)),
            ("💧", "Thirst", self._thirst, QColor(80,  190, 255), QColor(40, 110, 210)),
            ("💤", "Sleep",  self._sleep,  QColor(170, 110, 255), QColor(100, 50, 190)),
        ]

        bar_x   = pad
        bar_w   = W - pad * 2
        bar_h   = 10
        label_w = 70

        for i, (icon, name, val, full_c, low_c) in enumerate(stats):
            row_y = 174 + i * 34

            p.setFont(QFont("Segoe UI", 9))
            p.setPen(QColor(220, 220, 240))
            p.drawText(QRect(bar_x, row_y, label_w, 16), Qt.AlignmentFlag.AlignLeft, f"{icon} {name}")

            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            bar_col = full_c if val > 0.35 else low_c
            p.setPen(bar_col)
            p.drawText(QRect(bar_x, row_y, bar_w, 16), Qt.AlignmentFlag.AlignRight, f"{int(val * 100)}%")

            p.setBrush(QColor(45, 45, 65))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bar_x, row_y + 18, bar_w, bar_h, 4, 4)

            fill_w = max(6, int(bar_w * val))
            p.setBrush(bar_col)
            p.drawRoundedRect(bar_x, row_y + 18, fill_w, bar_h, 4, 4)

            dot_col = self._status_dot_color(val)
            p.setBrush(dot_col)
            p.drawEllipse(bar_x + label_w + 4, row_y + 2, 8, 8)

        p.setPen(QPen(QColor(60, 60, 100), 1))
        p.drawLine(pad, self.height() - 30, W - pad, self.height() - 30)
        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QColor(90, 90, 130))
        p.drawText(
            QRect(pad, self.height() - 24, W - pad * 2, 16),
            Qt.AlignmentFlag.AlignCenter,
            "Click ✕ or outside to close"
        )


class _ClickOutsideFilter(QObject):
    """Hides the InfoPanel when the user clicks anywhere outside it."""
    def __init__(self, panel: InfoPanel):
        super().__init__(panel)
        self._panel = panel

    def eventFilter(self, obj, event):
        if (self._panel.isVisible()
                and event.type() == QEvent.Type.MouseButtonPress):
            # Map the click to global coords
            try:
                global_pos = event.globalPosition().toPoint()
            except AttributeError:
                global_pos = event.globalPos()
            panel_rect = QRect(self._panel.pos(), self._panel.size())
            if not panel_rect.contains(global_pos):
                self._panel.hide()
        return False  # never consume the event


class Pet(QLabel):

    STATE_AFK  = "afk"
    STATE_BUSY = "busy"

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        def load(paths):
            frames = []
            for path in paths:
                px = QPixmap(path).scaled(
                    150, 150,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                if px.isNull():
                    print(f"WARNING: could not load '{path}'")
                frames.append(px)
            return frames

        self.idle_frames    = load(["nino.jpg",    "nino1.jpg"])
        self.walk_frames    = load(["nino.jpg",    "nino1.jpg"])
        self.sleep_frames   = load(["sleep.jpg"])
        self.sneak_frames   = load(["sneaky.jpg"])
        self.eating_frames  = load(["eating.jpg"])

        self.frame_index  = 0
        self._is_walking  = False
        self._is_sleeping = False
        self._is_sneaking = False
        self._is_eating   = False
        self._eat_revert_timer = QTimer(self)
        self._eat_revert_timer.setSingleShot(True)
        self._eat_revert_timer.timeout.connect(self._stop_eating_anim)

        self.setPixmap(self.idle_frames[0])
        self.resize(self.idle_frames[0].width(), self.idle_frames[0].height())

        self._hunger = 1.0
        self._thirst = 1.0
        self._sleep  = 1.0

        self._auto_feeding  = False
        self._auto_drinking = False

        self.bubble     = SpeechBubble()
        self.panel      = StatsPanel()
        self.info_panel = InfoPanel()
        self.panel.set_stats(self._hunger, self._thirst, self._sleep)
        self.panel.show()
        self._sync_overlays()

        self.drag_position = QPoint()
        self._direction    = 1

        self._activity_state    = self.STATE_AFK
        self._last_mouse_pos    = QPoint(-1, -1)
        self._mouse_still_ms    = 0
        self._mouse_moving_ms   = 0
        self._going_to_corner   = False
        self._corner_target     = QPoint()
        self._corner_timer      = None

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick_animation)
        self.anim_timer.start(400)

        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self._tick_movement)
        self.physics_timer.start(PHYSICS_MS)

        self.walk_timer = QTimer(self)
        self.walk_timer.setSingleShot(True)
        self.walk_timer.timeout.connect(self._start_rest)

        self.rest_timer = QTimer(self)
        self.rest_timer.setSingleShot(True)
        self.rest_timer.timeout.connect(self._start_walk)

        self.stat_timer = QTimer(self)
        self.stat_timer.timeout.connect(self._drain_stats)
        self.stat_timer.start(STAT_DRAIN_MS)

        self.sleep_restore_timer = QTimer(self)
        self.sleep_restore_timer.timeout.connect(self._restore_sleep)
        self.sleep_restore_timer.start(SLEEP_RESTORE_MS)

        self.quip_timer = QTimer(self)
        self.quip_timer.timeout.connect(self._idle_quip)
        self.quip_timer.start(QUIP_MS)

        self.afk_timer = QTimer(self)
        self.afk_timer.timeout.connect(self._check_activity)
        self.afk_timer.start(AFK_CHECK_MS)

        self._info_panel_refresh_timer = QTimer(self)
        self._info_panel_refresh_timer.timeout.connect(self._refresh_info_panel_if_visible)
        self._info_panel_refresh_timer.start(500)

        self._start_walk()

    # ── helpers ─────────────────────────────────────────────────────────────

    def _current_frames(self):
        if self._is_eating:   return self.eating_frames
        if self._is_sleeping: return self.sleep_frames
        if self._is_sneaking: return self.sneak_frames
        if self._is_walking:  return self.walk_frames
        return self.idle_frames

    def _start_eating_anim(self):
        self._is_eating = True
        self._eat_revert_timer.start(EAT_SPRITE_DURATION_MS)

    def _stop_eating_anim(self):
        self._is_eating = False

    def _check_activity(self):
        try:
            cur = QCursor.pos()
        except Exception:
            mx, my = pyautogui.position()
            cur = QPoint(mx, my)

        moved = (cur != self._last_mouse_pos)
        self._last_mouse_pos = cur

        if moved:
            self._mouse_moving_ms += AFK_CHECK_MS
            self._mouse_still_ms   = 0
        else:
            self._mouse_still_ms  += AFK_CHECK_MS
            self._mouse_moving_ms  = 0

        if self._activity_state == self.STATE_AFK:
            if self._mouse_moving_ms >= BUSY_THRESHOLD_MS:
                self._on_user_active()
        else:
            if self._mouse_still_ms >= AFK_THRESHOLD_MS:
                self._on_user_afk()

    def _refresh_info_panel_if_visible(self):
        if self.info_panel.isVisible():
            self._refresh_info_panel()

    def _on_user_active(self):
        if self._going_to_corner:
            return
        self._activity_state  = self.STATE_BUSY
        self._mouse_moving_ms = 0
        self._is_walking = False
        self.walk_timer.stop()
        self.rest_timer.stop()
        if not self._is_sleeping:
            self._say("I'll stay out of your way! 🐾", 2500)
            self._walk_to_corner()

    def _on_user_afk(self):
        self._activity_state = self.STATE_AFK
        self._mouse_still_ms = 0
        if self._is_sleeping:
            self._wake_up()
        else:
            self._say("You're back! 🐾", 2000)
            self._start_walk()

    def _corner_pos(self):
        sr = QApplication.primaryScreen().availableGeometry()
        return QPoint(
            sr.width()  - self.width()  - CORNER_MARGIN,
            sr.height() - self.height() - CORNER_MARGIN
        )

    def _walk_to_corner(self):
        self._going_to_corner = True
        self._is_sneaking     = True
        self._corner_target   = self._corner_pos()
        self._corner_step     = 0
        self._corner_start    = self.pos()
        dx   = self._corner_target.x() - self._corner_start.x()
        dy   = self._corner_target.y() - self._corner_start.y()
        dist = max(1, int((dx * dx + dy * dy) ** 0.5))
        self._corner_steps = max(20, dist // CORNER_STEP_PX)
        if self._corner_timer is not None:
            self._corner_timer.stop()
        self._corner_timer = QTimer(self)
        self._corner_timer.timeout.connect(self._step_to_corner)
        self._corner_timer.start(PHYSICS_MS)

    def _step_to_corner(self):
        if self._corner_step >= self._corner_steps:
            self._corner_timer.stop()
            self._going_to_corner = False
            self._is_sneaking     = False
            self._is_walking      = False
            if self._activity_state == self.STATE_BUSY:
                self._go_sleep()
            return
        t  = self._corner_step / self._corner_steps
        nx = int(self._corner_start.x() + (self._corner_target.x() - self._corner_start.x()) * t)
        ny = int(self._corner_start.y() + (self._corner_target.y() - self._corner_start.y()) * t)
        self.move(nx, ny)
        self._sync_overlays()
        self._corner_step += 1
        self._is_walking   = True

    def _start_walk(self):
        if self._is_sleeping:            return
        if self._activity_state == self.STATE_BUSY: return
        if self._going_to_corner:        return
        self._is_walking = True
        self._direction  = random.choice([-1, 1])
        self.walk_timer.start(WALK_DURATION_MS)

    def _start_rest(self):
        self._is_walking = False
        self._say(random.choice(REST_QUIPS))
        self.rest_timer.start(REST_DURATION_MS)

    def _go_sleep(self):
        self._is_sleeping = True
        self._is_walking  = False
        self.walk_timer.stop()
        self.rest_timer.stop()
        self._say(random.choice(SLEEP_QUIPS), 3000)

    def _wake_up(self):
        self._is_sleeping = False
        self._say("Good morning! 🌞", 2000)
        if self._activity_state == self.STATE_AFK:
            QTimer.singleShot(2200, self._start_walk)

    def _auto_feed(self):
        self._hunger       = min(1.0, self._hunger + AUTOFEED_AMOUNT)
        self._auto_feeding = False
        self.panel.set_stats(self._hunger, self._thirst, self._sleep)
        self._start_eating_anim()
        self._say(random.choice(AUTOFEED_QUIPS), 2500)

    def _auto_drink(self):
        self._thirst        = min(1.0, self._thirst + AUTODRINK_AMOUNT)
        self._auto_drinking = False
        self.panel.set_stats(self._hunger, self._thirst, self._sleep)
        self._start_eating_anim()
        self._say(random.choice(AUTODRINK_QUIPS), 2500)

    def _sync_overlays(self):
        pos = self.pos()
        px  = pos.x() + self.width() + 8
        py  = pos.y()
        sr  = QApplication.primaryScreen().availableGeometry()
        if px + self.panel.width() > sr.width():
            px = pos.x() - self.panel.width() - 8
        self.panel.move(px, py)
        self.bubble.move_to(self._bubble_anchor())

    def _bubble_anchor(self) -> QPoint:
        return self.mapToGlobal(QPoint(self.width() // 2, 0))

    def _say(self, text: str, duration: int = 2500):
        self.bubble.say(text, self._bubble_anchor(), duration)

    def _state_label(self) -> str:
        if self._is_eating:                        return "Eating"
        if self._is_sleeping:                      return "Sleeping"
        if self._is_sneaking or self._going_to_corner: return "Hiding"
        if self._is_walking:                       return "Roaming"
        return "Resting" if not self.rest_timer.isActive() else "Idle"

    def _refresh_info_panel(self):
        self.info_panel.update_data(
            self._hunger, self._thirst, self._sleep,
            self._state_label(),
            "Working" if self._activity_state == self.STATE_BUSY else "Away",
            self._is_sleeping,
            self._is_eating,
            self._activity_state == self.STATE_BUSY,
        )

    def _tick_animation(self):
        frames = self._current_frames()
        self.frame_index = (self.frame_index + 1) % len(frames)
        self.setPixmap(frames[self.frame_index])

    def _tick_movement(self):
        if not self._is_walking:  return
        if self._going_to_corner: return
        if self._activity_state == self.STATE_BUSY:
            self._is_walking = False
            return
        sr  = QApplication.primaryScreen().availableGeometry()
        pos = self.pos()
        nx  = pos.x() + self._direction * STEP_PX
        if nx < 0 or nx + self.width() > sr.width():
            self._direction *= -1
            nx = pos.x() + self._direction * STEP_PX
        self.move(nx, pos.y())
        self._sync_overlays()

    def _drain_stats(self):
        if self._is_sleeping:
            self._hunger = max(0.0, self._hunger - 0.02)
            self._thirst = max(0.0, self._thirst - 0.02)
        else:
            self._hunger = max(0.0, self._hunger - 0.05)
            self._thirst = max(0.0, self._thirst - 0.06)
            self._sleep  = max(0.0, self._sleep  - 0.04)
        self.panel.set_stats(self._hunger, self._thirst, self._sleep)
        if self._sleep < 0.15 and not self._is_sleeping:
            self._go_sleep()
        elif self._hunger < AUTOFEED_THRESHOLD and not self._auto_feeding:
            self._auto_feeding = True
            self._say("I'm starving! Feeding myself… 🍖", 2000)
            QTimer.singleShot(2200, self._auto_feed)
        elif self._thirst < AUTODRINK_THRESHOLD and not self._auto_drinking:
            self._auto_drinking = True
            self._say("So thirsty! Getting water… 💧", 2000)
            QTimer.singleShot(2200, self._auto_drink)

    def _restore_sleep(self):
        if self._is_sleeping:
            self._sleep = min(1.0, self._sleep + 0.12)
            self.panel.set_stats(self._hunger, self._thirst, self._sleep)
            if self._sleep >= 1.0:
                self._wake_up()

    def _idle_quip(self):
        if not self._is_walking and not self._is_sleeping and self._activity_state == self.STATE_AFK:
            self._say(random.choice(IDLE_QUIPS))

    def _close_chrome(self):
        self._say("On it! 🐾", 1500)
        target = find_chrome_close_button()
        if not target:
            self._say("I can't find Chrome… 😕", 2500)
            return
        self.walk_timer.stop()
        self.rest_timer.stop()
        self._is_walking = False
        start  = self.pos()
        ex     = target.x() - self.width() // 2
        ey     = target.y() - self.height() // 2
        steps  = 40
        self._chrome_step   = 0
        self._chrome_target = target

        def step():
            if self._chrome_step > steps:
                self._chrome_walk_timer.stop()
                pyautogui.click(self._chrome_target.x(), self._chrome_target.y())
                self._say("Done! Chrome closed 😎", 2500)
                QTimer.singleShot(800, self._start_walk)
                return
            t  = self._chrome_step / steps
            nx = int(start.x() + (ex - start.x()) * t)
            ny = int(start.y() + (ey - start.y()) * t)
            self.move(nx, ny)
            self._sync_overlays()
            self._chrome_step += 1

        self._chrome_walk_timer = QTimer(self)
        self._chrome_walk_timer.timeout.connect(step)
        self._chrome_walk_timer.start(20)

    # ── Qt events ────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.physics_timer.stop()
            self.walk_timer.stop()
            self.rest_timer.stop()
            self._is_walking = False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.physics_timer.start(PHYSICS_MS)
            if self._activity_state == self.STATE_AFK and not self._is_sleeping:
                self._start_walk()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            self._sync_overlays()

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        if self.info_panel.isVisible():
            status_action = menu.addAction("Close Status 📊")
        else:
            status_action = menu.addAction("Open Status 📊")

        menu.addSeparator()
        feed_action   = menu.addAction("Feed 🍖")
        drink_action  = menu.addAction("Give water 💧")
        sleep_action  = menu.addAction("Wake up 🌞" if self._is_sleeping else "Sleep 💤")
        menu.addSeparator()
        chrome_action = menu.addAction("Close Chrome 🌐")
        menu.addSeparator()
        exit_action   = menu.addAction("Exit ✕")

        action = menu.exec(event.globalPos())

        if action == status_action:
            if self.info_panel.isVisible():
                self.info_panel.hide()
            else:
                self._refresh_info_panel()
                self.info_panel.show_at(event.globalPos())
        elif action == exit_action:
            QApplication.quit()
        elif action == feed_action:
            self._hunger = min(1.0, self._hunger + 0.40)
            self.panel.set_stats(self._hunger, self._thirst, self._sleep)
            self._start_eating_anim()
            self._say(random.choice(FEED_QUIPS))
        elif action == drink_action:
            self._thirst = min(1.0, self._thirst + 0.45)
            self.panel.set_stats(self._hunger, self._thirst, self._sleep)
            self._start_eating_anim()
            self._say(random.choice(DRINK_QUIPS))
        elif action == sleep_action:
            if self._is_sleeping:
                self._wake_up()
            else:
                self._go_sleep()
        elif action == chrome_action:
            self._close_chrome()

    def closeEvent(self, event):
        self.bubble.close()
        self.panel.close()
        self.info_panel.close()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = Pet()
    pet.show()
    sys.exit(app.exec())