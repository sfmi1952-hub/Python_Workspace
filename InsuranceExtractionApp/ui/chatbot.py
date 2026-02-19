from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QLineEdit, QPushButton, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt

class ChatBotDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 약관 챗봇")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.resize(400, 550)
        self.setStyleSheet("""
            QDialog { background-color: white; border: 1px solid #ddd; border-radius: 15px; }
            QListWidget { border: none; background: #f8f9fa; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QFrame()
        header.setStyleSheet("background-color: #1428A0; border-top-left-radius: 15px; border-top-right-radius: 15px;")
        header.setFixedHeight(50)
        h_layout = QHBoxLayout(header)
        
        title = QLabel("AI 약관 챗봇")
        title.setStyleSheet("color: white; font-weight: bold;")
        h_layout.addWidget(title)
        
        close_btn = QPushButton("X")
        close_btn.setStyleSheet("color: white; font-weight: bold; background: transparent; border: none;")
        close_btn.clicked.connect(self.hide)
        h_layout.addWidget(close_btn)
        
        layout.addWidget(header)
        
        # Chat Area
        self.chat_area = QListWidget()
        layout.addWidget(self.chat_area)
        
        # Input Area
        input_frame = QFrame()
        input_layout = QHBoxLayout(input_frame)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("질문을 입력하세요...")
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field)
        
        send_btn = QPushButton("전송")
        send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(send_btn)
        
        layout.addWidget(input_frame)
        
        self.context_text = ""
        self.add_message("bot", "안녕하세요! AI 약관 챗봇입니다.")

    def set_context(self, text):
        self.context_text = text

    def add_message(self, sender, text):
        self.chat_area.addItem(f"{'User' if sender == 'user' else 'Bot'}: {text}")
        self.chat_area.scrollToBottom()

    def send_message(self):
        msg = self.input_field.text().strip()
        if not msg: return
        
        self.add_message("user", msg)
        self.input_field.clear()
        
        # AI Chat Logic
        if not hasattr(self, 'gemini_client') or not self.gemini_client or not self.gemini_client.model:
            # Fallback for Keyword matching (Simple logic)
            keywords = [w for w in msg.split() if len(w) > 1]
            lines = self.context_text.split('\n')
            matched = [l.strip() for l in lines if any(k in l for k in keywords)]
            
            if matched:
                result = matched[0] # Just show first match for now
                self.add_message("bot", f"관련 내용을 찾았습니다:\n{result}")
            else:
                self.add_message("bot", "죄송합니다. AI 모델이 로드되지 않았고 관련 내용을 찾지 못했습니다.")
            return

        # Gemini AI Chat
        try:
            self.add_message("bot", "생각 중...")
            
            # Construct Prompt
            chat_prompt = f"""
            당신은 유능한 보험 약관 분석 전문가입니다. 
            다음 제공된 '약관 원문'의 내용을 바탕으로 사용자의 질문에 친절하고 정확하게 답해주세요.
            
            [약관 원문]
            {self.context_text[:10000]} # Limit context somewhat for safety
            
            [질문]
            {msg}
            """
            
            response = self.gemini_client.model.generate_content(chat_prompt)
            
            # Remove "생각 중..." message and add real response
            last_item = self.chat_area.takeItem(self.chat_area.count() - 1)
            self.add_message("bot", response.text.strip())
            
        except Exception as e:
            self.add_message("bot", f"AI 분석 중 오류가 발생했습니다: {str(e)}")
