from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QSplitter
from PyQt6.QtCore import Qt
from ui.left_panel import LeftPanel
from ui.right_panel import RightPanel
from ui.chatbot import ChatBotDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Samsung Fire & Marine - AI Policy Parser POC")
        self.resize(1400, 900)
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        self.header = QFrame()
        self.header.setObjectName("HeaderFrame")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 0, 20, 0)
        
        title_label = QLabel("장기상품 약관 AI 정보추출 시스템")
        title_label.setObjectName("HeaderTitle")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        self.chat_btn = QPushButton("AI 약관 챗봇")
        self.chat_btn.setObjectName("ChatBotButton")
        self.chat_btn.clicked.connect(self.toggle_chat)
        header_layout.addWidget(self.chat_btn)
        
        main_layout.addWidget(self.header)

        # Content Area
        content_frame = QFrame()
        content_layout = QHBoxLayout(content_frame)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)
        
        # Splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.left_panel = LeftPanel()
        self.right_panel = RightPanel()
        
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        content_layout.addWidget(splitter)
        main_layout.addWidget(content_frame)

        # Chatbot Dialog (Hidden initially)
        self.chatbot = ChatBotDialog(self)
        
        # Signals
        # Signals
        # on_analyze is now ONLY for chatbot context, not for triggering RightPanel update immediately
        # self.left_panel.on_analyze.connect(self.right_panel.update_data) 
        
        self.left_panel.on_analyze_data.connect(self.right_panel.set_data) # Gemini Result
        self.left_panel.on_regex_fallback.connect(self.right_panel.update_data) # Regex Result (Fallback)
        
        self.left_panel.on_analyze.connect(self.pass_data_to_chatbot)

        # Gemini Setup
        self.check_api_key()

    def check_api_key(self):
        from PyQt6.QtWidgets import QInputDialog, QLineEdit
        import os
        from logic.gemini_client import GeminiClient
        
        # Simple check for env or prompt
        api_key = os.getenv("GEMINI_API_KEY")
        
        # Validation loop
        while True:
            # If we don't have a seemingly valid key (empty, contains spaces, or looks like an error msg)
            if not api_key or " " in api_key or "Error" in api_key:
                msg = "Google Gemini API Key를 입력하세요:"
                if api_key:
                    msg = f"잘못된 API Key 형식입니다.\n다시 입력하세요: (이전: {api_key[:10]}...)"
                
                key, ok = QInputDialog.getText(self, "Gemini API Key", 
                                             f"{msg}\n(입력하지 않으면 정규식 모드로 동작합니다)", 
                                             echo=QLineEdit.EchoMode.Password)
                if ok and key:
                    api_key = key.strip()
                else:
                    api_key = None # Canceled or empty
                    break
            else:
                break
        
        if api_key:
            self.left_panel.gemini_client = GeminiClient()
            self.left_panel.gemini_client.configure(api_key)
            self.chatbot.gemini_client = self.left_panel.gemini_client # Pass to chatbot
            self.setWindowTitle(self.windowTitle() + " [AI Mode: ON]")
        else:
            self.setWindowTitle(self.windowTitle() + " [AI Mode: OFF]")
    def toggle_chat(self):
        if self.chatbot.isVisible():
            self.chatbot.hide()
        else:
            # Position bottom right
            geo = self.geometry()
            x = geo.x() + geo.width() - 400 - 30
            y = geo.y() + geo.height() - 550 - 30
            self.chatbot.move(x, y)
            self.chatbot.show()

    def pass_data_to_chatbot(self, text):
        self.chatbot.set_context(text)
