# Simplified Gemini Client for Step 1 PoC
import google.generativeai as genai
import time
import os

class GeminiCore:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.model = None
        if api_key:
            self.configure(api_key)

    def configure(self, api_key):
        self.api_key = api_key
        # Force REST transport to avoid gRPC issues in corporate environments
        genai.configure(api_key=api_key, transport='rest')
        print(f"DEBUG: Configured Gemini with API Key: {api_key[:5]}... and transport='rest'")
        
        target_model = 'gemini-1.5-pro' # Ultimate fallback
        
        try:
            # Priority: Gemini 3 Pro > 1.5 Pro
            # We list models to see if 3.0 is available
            found_models = [m.name for m in genai.list_models()]
            
            # 1. Search for Gemini 3 Pro
            for m in found_models:
                if 'gemini-3-pro' in m.lower():
                    target_model = m
                    break
            
            # 2. If not found, look for 2.0 or experimental high-reasoning models
            if 'gemini-3' not in target_model:
                for m in found_models:
                    if 'gemini-2.0-flash-exp' in m:
                        target_model = m
                        break
        except Exception as e:
            print(f"Warning: Could not list models (check API key): {e}")
            # Fallback to 1.5 Pro which is widely available
            target_model = 'gemini-1.5-pro'
        
        print(f"DEBUG: Selected Gemini Model: {target_model}")
        self.model = genai.GenerativeModel(target_model)
        self.model_name = target_model # Store for logging

    def get_model_name(self):
        return self.model_name

    def upload_file(self, path, mime_type=None, logger=print):
        if not self.api_key: raise ValueError("API Key not configured")
        
        path_to_upload = path
        
        # Auto-convert Excel to CSV because Gemini often rejects .xlsx mime type
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.xlsx', '.xls']:
            try:
                import pandas as pd
                import tempfile
                logger(f"Converting Excel {os.path.basename(path)} to CSV for Gemini processing...")
                
                # Use openpyxl explicitly for .xlsx
                engine = 'openpyxl' if ext == '.xlsx' else None
                df = pd.read_excel(path, engine=engine)
                
                # Create temp CSV
                fd, csv_path = tempfile.mkstemp(suffix=".csv")
                os.close(fd)
                df.to_csv(csv_path, index=False)
                
                path_to_upload = csv_path
                mime_type = 'text/csv'
                logger(f"  > Conversion successful: {os.path.basename(csv_path)}")
            except Exception as e:
                logger(f"  > Warning: Excel conversion failed ({e}). Uploading original.")
                mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

        # Explicitly determine MIME type if not provided/overridden
        if not mime_type:
            ext = os.path.splitext(path_to_upload)[1].lower()
            if ext == '.pdf':
                mime_type = 'application/pdf'
            elif ext == '.csv':
                mime_type = 'text/csv'
            elif ext in ['.txt', '.md']:
                mime_type = 'text/plain'

        logger(f"Uploading {os.path.basename(path_to_upload)} (MIME: {mime_type})...")
        f = genai.upload_file(path_to_upload, mime_type=mime_type)
        
        while f.state.name == "PROCESSING":
            time.sleep(1)
            f = genai.get_file(f.name)
        
        if f.state.name != "ACTIVE":
            raise Exception(f"File upload failed: {f.state.name}")
            
        logger(f"  > File active: {f.name}")
        return f
