from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QPushButton, QLabel, 
                             QFileDialog, QTextEdit, QProgressBar, QMessageBox, QHBoxLayout)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from logic.gemini_client import GeminiClient
from logic.pdf_loader import extract_text_from_pdf

# Worker for RAG Analysis
class GeminiWorker(QThread):
    finished = pyqtSignal(dict)
    log_signal = pyqtSignal(str)

    def __init__(self, client, target_path, ref_paths):
        super().__init__()
        self.client = client
        self.target_path = target_path
        self.ref_paths = ref_paths

    def run(self):
        def logger(msg):
            self.log_signal.emit(msg)
            
        data = self.client.extract_data(self.target_path, self.ref_paths, logger=logger)
        self.finished.emit(data)

class LeftPanel(QFrame):
    on_analyze = pyqtSignal(str)      # Emits full text (for Chatbot context)
    on_analyze_data = pyqtSignal(dict) # Emits extracted data (for RightPanel)
    on_regex_fallback = pyqtSignal(str) # Emits text for Regex Fallback

    def __init__(self):
        super().__init__()
        self.setObjectName("LeftPanel")
        
        self.gemini_client = None # Will be set by MainWindow
        self.current_pdf_path = None
        self.reference_paths = [] # Changed from single rule path to list
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header Area
        header = QFrame()
        header.setStyleSheet("background-color: #f8f9fa; border-bottom: 1px solid #eee;")
        header.setFixedHeight(100) # Increased height for two rows
        
        v_header = QVBoxLayout(header)
        
        # Row 1: PDF Upload (Input Target)
        h_layout1 = QHBoxLayout()
        self.filename_label = QLabel("분석 대상(New PDF) 없음")
        self.filename_label.setStyleSheet("font-weight: bold; color: #555;")
        h_layout1.addWidget(self.filename_label)
        h_layout1.addStretch()
        self.upload_btn = QPushButton("📄 대상 PDF 업로드")
        self.upload_btn.setObjectName("UploadButton")
        self.upload_btn.clicked.connect(self.upload_file)
        h_layout1.addWidget(self.upload_btn)
        v_header.addLayout(h_layout1)

        # Row 2: Reference Files Upload
        h_layout2 = QHBoxLayout()
        self.ref_label = QLabel("참조 파일(Old PDF, Excel) 없음")
        self.ref_label.setStyleSheet("color: #777; font-size: 11px;")
        h_layout2.addWidget(self.ref_label)
        h_layout2.addStretch()
        self.ref_btn = QPushButton("📚 참조 파일 업로드 (다중 선택)")
        self.ref_btn.setStyleSheet("""
            background-color: #2196F3; color: white; border-radius: 6px; padding: 4px 8px; font-size: 11px;
        """)
        self.ref_btn.clicked.connect(self.upload_references)
        h_layout2.addWidget(self.ref_btn)
        v_header.addLayout(h_layout2)
        
        layout.addWidget(header)
        
        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0) # Infinite loading
        layout.addWidget(self.progress)
        
        # Text Editor
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("대상 PDF를 업로드하면 Gemini가 텍스트를 추출하여 표시합니다.\n(API Key 필요)")
        layout.addWidget(self.text_edit)
        
        # Log Console (New)
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(100)
        self.log_console.setStyleSheet("""
            background-color: #263238; color: #80cbc4; font-family: Consolas, monospace; font-size: 11px; border-top: 2px solid #37474f;
        """)
        self.log_console.setPlaceholderText("Execution logs will appear here...")
        layout.addWidget(self.log_console)
        
        # Analyze Button
        self.analyze_btn = QPushButton("🔍 분석 시작 (Analyze)")
        self.analyze_btn.setStyleSheet("""
            background-color: #1428A0; color: white; font-size: 14px; font-weight: bold; padding: 10px; border-radius: 0;
        """)
        self.analyze_btn.clicked.connect(self.run_analyze)
        layout.addWidget(self.analyze_btn)

    def upload_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Open Target PDF', 'c:\\', "PDF files (*.pdf)")
        if fname:
            self.current_pdf_path = fname
            self.filename_label.setText(f"대상: {fname.split('/')[-1]}")
            self.filename_label.setStyleSheet("font-weight: bold; color: #1428A0;")
            
            # Extract Text for preview (Local pdfplumber - Cost saving)
            text = extract_text_from_pdf(fname)
            self.text_edit.setText(text)

    def upload_references(self):
        fnames, _ = QFileDialog.getOpenFileNames(self, 'Open Reference Files', 'c:\\', "All Supported (*.pdf *.xlsx *.xls);;PDF (*.pdf);;Excel (*.xlsx *.xls)")
        if fnames:
            self.reference_paths = fnames
            self.ref_label.setText(f"참조 파일 {len(fnames)}개 선택됨")
            self.ref_label.setStyleSheet("font-weight: bold; color: #2e7d32; font-size: 11px;")
            self.log_console.append(f">>> Selected {len(fnames)} reference files.")

    def run_analyze(self):
        text = self.text_edit.toPlainText()
        if not text:
            QMessageBox.warning(self, "Warning", "분석할 텍스트가 없습니다.")
            return

        # Emit text for Chatbot context
        self.on_analyze.emit(text)

        if self.gemini_client and self.current_pdf_path:
            # Run Gemini RAG
            self.progress.setVisible(True)
            self.analyze_btn.setEnabled(False)
            self.analyze_btn.setText("AI 분석 중... (Context Uploading...)")
            
            # Clear previous result in Right Panel
            self.on_analyze_data.emit({})

            self.worker = GeminiWorker(self.gemini_client, self.current_pdf_path, self.reference_paths)
            self.worker.finished.connect(self.handle_gemini_result)
            self.worker.log_signal.connect(self.append_log) # Connect log
            self.log_console.clear()
            self.log_console.append(">>> Starting Gemini Analysis...")
            self.worker.start()
        else:
            # Fallback to Regex
            self.log_console.append(">>> Starting Regex Analysis (No AI)...")
            if not self.gemini_client:
                QMessageBox.information(self, "Info", "Gemini API 키가 없어 정규식(Regex) 모드로 실행합니다.")
            else:
                 QMessageBox.information(self, "Info", "PDF 파일 경로가 유실되어 텍스트 기반 정규식 모드로 실행합니다.")
            
            # Emit Signal to Run Regex in RightPanel
            self.on_regex_fallback.emit(text)
            
            # Use QTimer to simulate short processing
            self.analyze_btn.setText("분석 완료!")
            QTimer.singleShot(1000, lambda: self.analyze_btn.setText("🔍 분석 시작 (Analyze)"))


    def handle_gemini_result(self, data):
        self.progress.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("🔍 분석 시작 (Analyze)")
        
        if "error" in data:
            self.log_console.append(f"!!! Error: {data['error']}")
            QMessageBox.critical(self, "AI Error", f"Gemini 분석 중 오류 발생:\n{data['error']}")
        else:
            self.log_console.append(">>> Analysis Finished Successfully.")
        
        self.on_analyze_data.emit(data)

    def append_log(self, msg):
        self.log_console.append(msg)
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())
