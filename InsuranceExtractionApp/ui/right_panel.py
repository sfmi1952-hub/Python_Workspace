from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFrame, QLabel, QScrollArea, 
                             QGridLayout, QLineEdit, QTextEdit, QHBoxLayout, QPushButton)
from PyQt6.QtCore import Qt
from logic.parser import parse_text_to_data # Will implement later

class RightPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("RightPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self.grid = QGridLayout(container)
        self.grid.setContentsMargins(20, 20, 20, 20)
        self.grid.setSpacing(15)

        # Fields storage
        self.fields = {}
        
        # Defines the form structure
        self.field_defs = [
            ("benefitType", "Benefit Type", 0, 0, 1),
            ("benefitName", "Benefit Name", 0, 1, 1),
            ("node", "Node", 1, 0, 1),
            ("accidentType", "Accident Type", 1, 1, 1),
            ("coverageCode", "Coverage Code", 2, 0, 1),
            ("hospital", "Hospital", 2, 1, 1),
            ("diagnosisCode", "Diagnosis Code", 3, 0, 2), # Full width
            ("surgeryCode", "Surgery Code", 4, 0, 1),
            ("ediCode", "EDI Code", 4, 1, 1),
            ("reduction", "Reduction (1Y)", 5, 0, 1),
            ("limit", "Limit", 5, 1, 1),
            ("formula", "Formula", 6, 0, 2), # Full width
            ("source_evidence", "Source Evidence (Page/Quote)", 7, 0, 2) # New Field
        ]

        # Init Fields with PLACEHOLDER WIDGETS
        # Actual widgets should be recreated or updated dynamically
        for key, label, row, col, span in self.field_defs:
            self.create_field(key, label, row, col, span)

        # Footer Actions
        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        
        self.download_btn = QPushButton("Download Excel/CSV")
        footer_layout.addWidget(self.download_btn)
        
        layout.addWidget(footer)

    def create_field(self, key, label_text, row, col, span):
        wrapper = QFrame()
        wrapper.setStyleSheet("""
            background-color: white; 
            border: 1px solid #e0e0e0; 
            border-radius: 8px;
        """)
        wrapper.setMinimumHeight(80)
        
        vbox = QVBoxLayout(wrapper)
        vbox.setContentsMargins(15, 10, 15, 10)
        
        lbl = QLabel(label_text)
        lbl.setObjectName("FieldLabel")
        vbox.addWidget(lbl)
        
        if key in ["diagnosisCode", "formula", "source_evidence"]:
            inp = QTextEdit()
            inp.setObjectName("DataInput")
            inp.setMaximumHeight(80)
        else:
            inp = QLineEdit()
            inp.setObjectName("DataInput")
            
        vbox.addWidget(inp)
        
        self.grid.addWidget(wrapper, row, col, 1, span)
        self.fields[key] = inp

    def update_data(self, text):
        # Call parser logic (Regex Fallback)
        data = parse_text_to_data(text)
        self.set_data(data)

    def set_data(self, data):
        # Prevent errors if data contains 'error' key
        if "error" in data:
            self.fields["benefitName"].setText(f"Error: {data['error']}")
            return

        for key, value in data.items():
            if key in self.fields:
                widget = self.fields[key]
                if isinstance(widget, QLineEdit):
                    widget.setText(str(value))
                elif isinstance(widget, QTextEdit):
                    widget.setText(str(value))
