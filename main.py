import sys
from PyQt6.QtWidgets import QApplication, QLabel, QMenu
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QPixmap


class Pet(QLabel):
    def __init__(self):
        super().__init__()

    
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

   
        self.frames = [
    QPixmap("nino.jpg").scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation),
    QPixmap("nino1.jpg").scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
]
        for i, frame in enumerate(self.frames):
            if frame.isNull():
                print(f"ERROR: Frame {i} failed to load")


        self.frame_index = 0
        self.setPixmap(self.frames[self.frame_index])

     
        self.resize(self.frames[0].width(), self.frames[0].height())

  
        self.drag_position = QPoint()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(400)  

   
    def update_animation(self):
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.setPixmap(self.frames[self.frame_index])

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

   
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(
                event.globalPosition().toPoint() - self.drag_position
            )

  
    def contextMenuEvent(self, event):
        menu = QMenu(self)

        feed_action = menu.addAction("Feed ")
        sleep_action = menu.addAction("Sleep ")
        exit_action = menu.addAction("Exit ")

        action = menu.exec(event.globalPos())

        if action == exit_action:
            QApplication.quit()
        elif action == feed_action:
            print("Pet fed ")
        elif action == sleep_action:
            print("Pet sleeping ")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    pet = Pet()
    pet.show()

    sys.exit(app.exec())

