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
        genai.configure(api_key=api_key)
        
        # Strategy:
        # Tier 1 (Primary): Gemini 3.0 Pro -> 3.0 Pro Experimental
        # Tier 2 (Mid): Gemini 2.5 Pro -> 1.5 Pro
        # Tier 3 (Fast): Gemini 3.0 Flash -> 2.0 Flash -> 1.5 Flash
        
        self.available_models = []
        try:
            self.available_models = [m.name for m in genai.list_models()]
        except Exception as e:
            print(f"Warning: Could not list models (check API key): {e}")

        # 1. Select Initial Primary Model
        target_model = self._find_model_by_keyword(['gemini-3.0-pro', 'gemini-3-pro'])
        if not target_model:
            # Fallback to 1.5 Pro as 'Primary' if 3.0 not found
             target_model = 'gemini-1.5-pro'
        
        print(f"DEBUG: Selected Initial Gemini Model: {target_model}")
        self.model = genai.GenerativeModel(target_model)
        self.model_name = target_model 

    def _find_model_by_keyword(self, keywords):
        """Helper to find the first available model containing any of the keywords"""
        for k in keywords:
            for m in self.available_models:
                if k.lower() in m.lower():
                    return m
        return None

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

    def generate_content(self, contents, request_options=None, retries=3, base_delay=10):
        """
        Wrapper for model.generate_content with 3-stage fallback for 429 errors.
        Chain: 3.0 Pro -> 2.5 Pro -> 3.0 Flash
        """
        if not self.model:
             raise ValueError("Model not initialized")
             
        current_delay = base_delay
        
        for attempt in range(retries):
            try:
                # Add a small buffer before every request to be polite
                if attempt > 0: 
                    time.sleep(current_delay)
                
                response = self.model.generate_content(contents, request_options=request_options)
                return response
                
            except Exception as e:
                # Check for Quota/Rate Limit Error OR Server Errors
                err_str = str(e).lower()
                retry_keywords = ["429", "resource has been exhausted", "quota"]
                server_error_keywords = ["503", "504", "deadline exceeded", "timeout", "service unavailable"]
                
                is_rate_limit = any(k in err_str for k in retry_keywords)
                is_server_error = any(k in err_str for k in server_error_keywords)

                if is_rate_limit:
                    print(f"WARNING: API Quota Hit ({e}).")
                    
                    # --- Fallback Logic ---
                    # Current Strategy: 3.0 Pro -> 2.5/1.5 Pro -> 3.0/2.0 Flash
                    
                    next_model = None
                    curr = self.model_name.lower()
                    
                    # 1. Check if we are at Tier 1 (3.0 Pro / Primary)
                    # Implementation detail: generic detection if we are not yet on 'fallback' tiers
                    if "flash" not in curr and ("2.5" not in curr and "1.5" not in curr):
                        # Attempt switch to Tier 2 (2.5 Pro or 1.5 Pro)
                        print("  > Tier 1 Exhausted. Switching to Tier 2 (2.5/1.5 Pro)...")
                        
                        # Find 2.5 Pro
                        tier2 = self._find_model_by_keyword(['gemini-2.5-pro', 'gemini-2.5'])
                        if not tier2: tier2 = 'gemini-1.5-pro'
                        
                        next_model = tier2

                    # 2. Check if we are at Tier 2 (2.5 or 1.5 Pro)
                    elif ("2.5" in curr or "1.5" in curr) and "flash" not in curr:
                         print("  > Tier 2 Exhausted. Switching to Tier 3 (Flash)...")
                         
                         # Find 3.0 Flash first
                         tier3 = self._find_model_by_keyword(['gemini-3.0-flash', 'gemini-3-flash'])
                         
                         # Fallback to 2.0 Flash
                         if not tier3:
                             tier3 = self._find_model_by_keyword(['gemini-2.0-flash'])
                        
                         if not tier3: tier3 = 'gemini-1.5-flash'
                         
                         next_model = tier3

                    if next_model and next_model != self.model_name:
                         try:
                             print(f"  > Switching Model: {self.model_name} -> {next_model}")
                             self.model = genai.GenerativeModel(next_model)
                             self.model_name = next_model
                             print(f"  > Switched successfully. Retrying execution immediately...")
                             time.sleep(1)
                             continue # Retry loop immediately
                         except Exception as switch_err:
                             print(f"  > Failed to switch model: {switch_err}")

                    print(f"  > Retrying in {current_delay}s... (Attempt {attempt+1}/{retries})")
                    time.sleep(current_delay)
                    current_delay *= 2 # Exponential Backoff
                    
                elif is_server_error:
                     print(f"WARNING: Server Error ({e}). Retrying in {current_delay}s... (Attempt {attempt+1}/{retries})")
                     time.sleep(current_delay)
                     current_delay *= 2
                else:
                    # If it's not a 429 or 5xx, raise it immediately
                    raise e
                    
        raise Exception(f"Failed to generate content after {retries} retries due to quota exhaustion.")
