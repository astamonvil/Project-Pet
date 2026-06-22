import sys
import random
import ctypes
import ctypes.wintypes
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QWidget
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
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

AFK_CHECK_MS      = 1000   # how often we check mouse movement
AFK_THRESHOLD_MS  = 10000  # 10 s of no movement = AFK
BUSY_THRESHOLD_MS = 3000   # 3 s of movement = user is working
CORNER_MARGIN     = 12     # px from screen edge when hiding in corner
CORNER_STEP_PX    = 6      # speed when walking to corner

# Auto-feed/drink thresholds
AUTOFEED_THRESHOLD  = 0.15   # feed self when hunger drops below this
AUTODRINK_THRESHOLD = 0.15   # drink self when thirst drops below this
AUTOFEED_AMOUNT     = 0.50
AUTODRINK_AMOUNT    = 0.50


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

        self.idle_frames = load(["nino.jpg", "nino1.jpg"])
        self.walk_frames = load(["nino.jpg", "nino1.jpg"])

        self.frame_index  = 0
        self._is_walking  = False
        self._is_sleeping = False
        self.setPixmap(self.idle_frames[0])
        self.resize(self.idle_frames[0].width(), self.idle_frames[0].height())

        self._hunger = 1.0
        self._thirst = 1.0
        self._sleep  = 1.0

        # Cooldown flags so auto-feed/drink don't spam
        self._auto_feeding  = False
        self._auto_drinking = False

        self.bubble = SpeechBubble()
        self.panel  = StatsPanel()
        self.panel.set_stats(self._hunger, self._thirst, self._sleep)
        self.panel.show()
        self._sync_overlays()

        self.drag_position = QPoint()
        self._direction    = 1

        # AFK / busy tracking
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

        self._start_walk()

    # ── AFK detection ────────────────────────────────────────────────────────

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
            # User started working — go hide in corner
            if self._mouse_moving_ms >= BUSY_THRESHOLD_MS:
                self._on_user_active()
        else:
            # User went AFK — come back out and play
            if self._mouse_still_ms >= AFK_THRESHOLD_MS:
                self._on_user_afk()

    def _on_user_active(self):
        """User is now working. Stop roaming, walk to corner, sleep there."""
        if self._going_to_corner:
            return                      # already heading there
        self._activity_state  = self.STATE_BUSY
        self._mouse_moving_ms = 0

        # Stop any current roaming
        self._is_walking = False
        self.walk_timer.stop()
        self.rest_timer.stop()

        if not self._is_sleeping:
            self._say("I'll stay out of your way! 🐾", 2500)
            self._walk_to_corner()

    def _on_user_afk(self):
        """User stopped — wake up and start roaming again."""
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
            self._is_walking      = False
            # Only sleep if still busy (user didn't go AFK mid-walk)
            if self._activity_state == self.STATE_BUSY:
                self._go_sleep()
            return

        t  = self._corner_step / self._corner_steps
        nx = int(self._corner_start.x() + (self._corner_target.x() - self._corner_start.x()) * t)
        ny = int(self._corner_start.y() + (self._corner_target.y() - self._corner_start.y()) * t)
        self.move(nx, ny)
        self._sync_overlays()
        self._corner_step  += 1
        self._is_walking    = True

    # ── Walk / rest cycle (AFK only) ─────────────────────────────────────────

    def _start_walk(self):
        """Begin roaming — only allowed when user is AFK and pet is not sleeping."""
        if self._is_sleeping:
            return
        if self._activity_state == self.STATE_BUSY:
            return
        if self._going_to_corner:
            return
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
        # Only start roaming if user is AFK
        if self._activity_state == self.STATE_AFK:
            QTimer.singleShot(2200, self._start_walk)

    # ── Auto feed / drink ────────────────────────────────────────────────────

    def _auto_feed(self):
        """Pet feeds itself when starving."""
        self._hunger     = min(1.0, self._hunger + AUTOFEED_AMOUNT)
        self._auto_feeding = False
        self.panel.set_stats(self._hunger, self._thirst, self._sleep)
        self._say(random.choice(AUTOFEED_QUIPS), 2500)

    def _auto_drink(self):
        """Pet drinks itself when parched."""
        self._thirst      = min(1.0, self._thirst + AUTODRINK_AMOUNT)
        self._auto_drinking = False
        self.panel.set_stats(self._hunger, self._thirst, self._sleep)
        self._say(random.choice(AUTODRINK_QUIPS), 2500)

    # ── Overlays ─────────────────────────────────────────────────────────────

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

    # ── Ticks ────────────────────────────────────────────────────────────────

    def _tick_animation(self):
        frames = self.walk_frames if self._is_walking else self.idle_frames
        self.frame_index = (self.frame_index + 1) % len(frames)
        self.setPixmap(frames[self.frame_index])

    def _tick_movement(self):
        # Only roam when AFK, not going to corner, and walking flag is set
        if not self._is_walking:
            return
        if self._going_to_corner:
            return
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

        # ── Auto sleep when exhausted ────────────────────────────────────────
        if self._sleep < 0.15 and not self._is_sleeping:
            self._go_sleep()

        # ── Auto feed when starving ──────────────────────────────────────────
        elif self._hunger < AUTOFEED_THRESHOLD and not self._auto_feeding:
            self._auto_feeding = True
            self._say("I'm starving! Feeding myself… 🍖", 2000)
            QTimer.singleShot(2200, self._auto_feed)

        # ── Auto drink when parched ──────────────────────────────────────────
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
        # Only quip when roaming freely as AFK, not sleeping
        if not self._is_walking and not self._is_sleeping and self._activity_state == self.STATE_AFK:
            self._say(random.choice(IDLE_QUIPS))

    # ── Chrome action ────────────────────────────────────────────────────────

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

    # ── Mouse / drag ─────────────────────────────────────────────────────────

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
            # Only resume roaming if AFK
            if self._activity_state == self.STATE_AFK and not self._is_sleeping:
                self._start_walk()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            self._sync_overlays()

    # ── Context menu ─────────────────────────────────────────────────────────

    def contextMenuEvent(self, event):
        menu          = QMenu(self)
        feed_action   = menu.addAction("Feed 🍖")
        drink_action  = menu.addAction("Give water 💧")
        sleep_action  = menu.addAction("Wake up 🌞" if self._is_sleeping else "Sleep 💤")
        menu.addSeparator()
        chrome_action = menu.addAction("Close Chrome 🌐")
        menu.addSeparator()
        exit_action   = menu.addAction("Exit ✕")

        action = menu.exec(event.globalPos())

        if action == exit_action:
            QApplication.quit()
        elif action == feed_action:
            self._hunger = min(1.0, self._hunger + 0.40)
            self.panel.set_stats(self._hunger, self._thirst, self._sleep)
            self._say(random.choice(FEED_QUIPS))
        elif action == drink_action:
            self._thirst = min(1.0, self._thirst + 0.45)
            self.panel.set_stats(self._hunger, self._thirst, self._sleep)
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
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = Pet()
    pet.show()
    sys.exit(app.exec())