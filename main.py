import sys
import random
from PyQt6.QtWidgets import (
    QApplication, QLabel, QMenu, QWidget, QVBoxLayout
)
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPainterPath, QPen


# ── Speech Bubble ──────────────────────────────────────────────────────────────

class SpeechBubble(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._text = ""
        self._padding = 12
        self._tail_h = 14
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def say(self, text: str, anchor: QPoint, duration_ms: int = 2500):
        """Show bubble with text, tail pointing down toward anchor."""
        self._text = text
        font = QFont("Segoe UI", 10, QFont.Weight.Medium)
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(text) + self._padding * 2
        text_h = fm.height() + self._padding * 2
        total_h = text_h + self._tail_h

        # Position bubble so tail tip sits above anchor
        x = anchor.x() - text_w // 2
        y = anchor.y() - total_h - 4
        self.setGeometry(x, y, text_w, total_h)
        self.update()
        self.show()
        self.hide_timer.start(duration_ms)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        bubble_h = h - self._tail_h
        r = 10  # corner radius

        path = QPainterPath()
        path.addRoundedRect(0, 0, w, bubble_h, r, r)

        # Tail triangle
        tail_cx = w // 2
        path.moveTo(tail_cx - 8, bubble_h)
        path.lineTo(tail_cx + 8, bubble_h)
        path.lineTo(tail_cx, h)
        path.closeSubpath()

        painter.setPen(QPen(QColor(180, 180, 200), 1.5))
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawPath(path)

        painter.setPen(QColor(50, 50, 70))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        painter.drawText(
            QRect(0, 0, w, bubble_h),
            Qt.AlignmentFlag.AlignCenter,
            self._text
        )


# ── Stats Overlay ──────────────────────────────────────────────────────────────

class StatsOverlay(QWidget):
    """Small HUD that floats near the pet showing hunger & mood bars."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(110, 44)
        self._hunger = 1.0   # 0.0 = starving, 1.0 = full
        self._mood   = 1.0   # 0.0 = sad,      1.0 = happy

    def set_stats(self, hunger: float, mood: float):
        self._hunger = max(0.0, min(1.0, hunger))
        self._mood   = max(0.0, min(1.0, mood))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background pill
        p.setBrush(QColor(30, 30, 45, 200))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)

        font = QFont("Segoe UI", 7, QFont.Weight.Bold)
        p.setFont(font)

        bar_x, bar_w, bar_h = 32, 70, 7
        for i, (label, value, full_col, low_col) in enumerate([
            ("🍖", self._hunger, QColor(100, 200, 120), QColor(220, 80, 80)),
            ("😊", self._mood,   QColor(100, 160, 240), QColor(220, 160, 60)),
        ]):
            y = 8 + i * 20
            # Emoji label
            p.setPen(QColor(220, 220, 240))
            p.drawText(4, y, 24, 14, Qt.AlignmentFlag.AlignCenter, label)
            # Track
            p.setBrush(QColor(60, 60, 80))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bar_x, y + 2, bar_w, bar_h, 3, 3)
            # Fill
            fill_col = full_col if value > 0.35 else low_col
            p.setBrush(fill_col)
            p.drawRoundedRect(bar_x, y + 2, int(bar_w * value), bar_h, 3, 3)


# ── Main Pet Widget ────────────────────────────────────────────────────────────

IDLE_QUIPS = [
    "I'm bored…", "*yawns*", "What's up?",
    "Pet me! 🐾", "I'm watching you 👀", "Zzzz…",
    "*stretches*", "Hello there!", "Feed me pls 🍗",
]

FEED_QUIPS  = ["Yum! 😋", "More please!", "So tasty! 🍖", "Nom nom nom~"]
SLEEP_QUIPS = ["Night night 💤", "ZZZ…", "Don't disturb me!", "Dreaming of food 🍗"]

WANDER_INTERVAL_MS   = 3000   # how often to pick a new target
WANDER_STEP_PX       = 4      # pixels moved per physics tick
PHYSICS_INTERVAL_MS  = 16     # ~60 fps movement
STAT_DRAIN_INTERVAL  = 8000   # hunger/mood drain tick
QUIP_INTERVAL        = 12000  # idle speech bubble


class Pet(QLabel):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # ── Frames ────────────────────────────────────────────────────────────
        # Two-frame idle and a simple "walk" tint (replace with real walk frames
        # if you have them — just add paths to walk_paths below).
        idle_paths = ["nino.jpg", "nino1.jpg"]
        walk_paths = ["nino.jpg", "nino1.jpg"]   # swap for dedicated walk frames

        def load(paths):
            frames = []
            for p in paths:
                px = QPixmap(p).scaled(
                    150, 150,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                if px.isNull():
                    print(f"WARNING: could not load '{p}'")
                frames.append(px)
            return frames

        self.idle_frames = load(idle_paths)
        self.walk_frames = load(walk_paths)

        self.frame_index = 0
        self._is_walking = False
        self.setPixmap(self.idle_frames[0])
        self.resize(self.idle_frames[0].width(), self.idle_frames[0].height())

        # ── Stats ─────────────────────────────────────────────────────────────
        self._hunger = 1.0
        self._mood   = 1.0

        # ── Sub-widgets ───────────────────────────────────────────────────────
        self.bubble = SpeechBubble()
        self.stats  = StatsOverlay()
        self.stats.set_stats(self._hunger, self._mood)
        self.stats.show()
        self._update_stats_pos()

        # ── Drag ──────────────────────────────────────────────────────────────
        self.drag_position = QPoint()

        # ── Wander state ──────────────────────────────────────────────────────
        self._target = QPoint()
        self._pick_new_target()

        # ── Timers ────────────────────────────────────────────────────────────
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick_animation)
        self.anim_timer.start(400)

        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self._tick_movement)
        self.physics_timer.start(PHYSICS_INTERVAL_MS)

        self.wander_timer = QTimer(self)
        self.wander_timer.timeout.connect(self._pick_new_target)
        self.wander_timer.start(WANDER_INTERVAL_MS)

        self.stat_timer = QTimer(self)
        self.stat_timer.timeout.connect(self._drain_stats)
        self.stat_timer.start(STAT_DRAIN_INTERVAL)

        self.quip_timer = QTimer(self)
        self.quip_timer.timeout.connect(self._idle_quip)
        self.quip_timer.start(QUIP_INTERVAL)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _screen_rect(self) -> QRect:
        screen = QApplication.primaryScreen().availableGeometry()
        return screen

    def _pick_new_target(self):
        sr = self._screen_rect()
        margin = 20
        tx = random.randint(margin, sr.width()  - self.width()  - margin)
        ty = random.randint(margin, sr.height() - self.height() - margin)
        self._target = QPoint(tx, ty)

    def _bubble_anchor(self) -> QPoint:
        """Top-center of the pet in global screen coordinates."""
        return self.mapToGlobal(QPoint(self.width() // 2, 0))

    def _say(self, text: str, duration: int = 2500):
        self.bubble.say(text, self._bubble_anchor(), duration)

    def _update_stats_pos(self):
        """Keep stats HUD just below the pet."""
        pos = self.pos()
        sx = pos.x() + (self.width() - self.stats.width()) // 2
        sy = pos.y() + self.height() + 4
        self.stats.move(sx, sy)

    # ── Timer callbacks ───────────────────────────────────────────────────────

    def _tick_animation(self):
        frames = self.walk_frames if self._is_walking else self.idle_frames
        self.frame_index = (self.frame_index + 1) % len(frames)
        self.setPixmap(frames[self.frame_index])

    def _tick_movement(self):
        pos = self.pos()
        dx = self._target.x() - pos.x()
        dy = self._target.y() - pos.y()
        dist = (dx * dx + dy * dy) ** 0.5

        if dist < WANDER_STEP_PX + 1:
            self._is_walking = False
            return

        self._is_walking = True
        nx = pos.x() + int(dx / dist * WANDER_STEP_PX)
        ny = pos.y() + int(dy / dist * WANDER_STEP_PX)
        self.move(nx, ny)
        self._update_stats_pos()

    def _drain_stats(self):
        self._hunger = max(0.0, self._hunger - 0.06)
        self._mood   = max(0.0, self._mood   - 0.04)
        self.stats.set_stats(self._hunger, self._mood)

        if self._hunger < 0.25:
            self._say("I'm hungry! 🍗", 3000)
        elif self._mood < 0.25:
            self._say("I'm feeling sad… 😢", 3000)

    def _idle_quip(self):
        # Only show a random quip when not already talking about stats
        if self._hunger >= 0.25 and self._mood >= 0.25:
            self._say(random.choice(IDLE_QUIPS))

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            # Pause wandering while dragging
            self.physics_timer.stop()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.physics_timer.start(PHYSICS_INTERVAL_MS)
            self._pick_new_target()   # pick a new wander target from new pos

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(
                event.globalPosition().toPoint() - self.drag_position
            )
            self._update_stats_pos()

    # ── Context menu ──────────────────────────────────────────────────────────

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        feed_action  = menu.addAction("Feed 🍖")
        sleep_action = menu.addAction("Sleep 💤")
        stats_action = menu.addAction(
            f"Stats  🍖 {int(self._hunger*100)}%  😊 {int(self._mood*100)}%"
        )
        stats_action.setEnabled(False)
        menu.addSeparator()
        exit_action  = menu.addAction("Exit ✕")

        action = menu.exec(event.globalPos())

        if action == exit_action:
            QApplication.quit()

        elif action == feed_action:
            self._hunger = min(1.0, self._hunger + 0.40)
            self._mood   = min(1.0, self._mood   + 0.10)
            self.stats.set_stats(self._hunger, self._mood)
            self._say(random.choice(FEED_QUIPS))

        elif action == sleep_action:
            self._mood = min(1.0, self._mood + 0.35)
            self.stats.set_stats(self._hunger, self._mood)
            self._say(random.choice(SLEEP_QUIPS), 3000)
            # Pause wandering briefly for a "sleep" moment
            self.physics_timer.stop()
            QTimer.singleShot(4000, lambda: self.physics_timer.start(PHYSICS_INTERVAL_MS))

    def closeEvent(self, event):
        self.bubble.close()
        self.stats.close()
        super().closeEvent(event)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = Pet()
    pet.show()
    sys.exit(app.exec())