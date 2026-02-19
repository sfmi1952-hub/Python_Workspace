import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from PyQt6.QtGui import QFontDatabase, QFont

def main():
    app = QApplication(sys.argv)
    
    # Load Stylesheet
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    style_path = os.path.join(base_dir, "resources", "style.qss")
    
    try:
        with open(style_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print(f"Warning: style.qss not found at {style_path}")

    # Set default font (attempting to match Noto Sans KR or fallback)
    font = app.font()
    font.setFamily("Malgun Gothic") # Standard Windows KR font
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
