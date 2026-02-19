import google.generativeai as genai
import time
import os
import json
import csv
import tempfile
import openpyxl
import mimetypes
import zipfile
import xml.etree.ElementTree as ET

class GeminiClient:
    def __init__(self):
        self.api_key = None
        self.model = None

    def configure(self, api_key):
        self.api_key = api_key
        genai.configure(api_key=api_key)
        # Dynamic Model Selection
        self.model = None
        
        print("DEBUG: Checking available models...")
        supported_models = []
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    supported_models.append(m.name)
                    print(f" - Found supported model: {m.name}")
        except Exception as e:
            print(f"Warning: Could not list models: {e}")

        # 0. Strict Priority: Find ANY Gemini 3 Pro variant first
        selected_model_name = None
        for m in supported_models:
            if 'gemini-3-pro' in m.lower():
                selected_model_name = m
                break

        # 1. Fallback to Priority List if no 3 Pro found
        if not selected_model_name:
            candidates = [
                'models/gemini-3-pro-preview',
                'models/gemini-3-flash-preview',
                'models/gemini-2.5-pro',
                'models/gemini-2.5-flash',
                'models/gemini-2.0-flash-exp',
                'models/gemini-1.5-pro',
                'models/gemini-1.5-flash',
                'models/gemini-pro'
            ]

            for cand in candidates:
                if cand in supported_models:
                    selected_model_name = cand
                    break
        
        # 2. Fuzzy match for 1.5 or newer if still nothing
        if not selected_model_name:
            for m in supported_models:
                if 'gemini-1.5' in m or 'gemini-2.0' in m or 'gemini-2.5' in m:
                    selected_model_name = m
                    break
        
        # 3. Final Fallback
        if not selected_model_name:
            if 'models/gemini-pro' in supported_models:
                selected_model_name = 'models/gemini-pro'
            else:
                selected_model_name = 'gemini-3-pro-preview' # Hope for the best

        print(f"DEBUG: Selected Model: {selected_model_name}")
        self.model = genai.GenerativeModel(selected_model_name)

    def upload_file(self, path, mime_type=None, logger=None):
        """Uploads a file to Gemini File API and waits for it to be active."""
        if not self.api_key:
            raise ValueError("API Key not set")

        original_path = path
        temp_csv = None

        # Handle Excel conversion to CSV (bypass MIME unsupported error)
        is_excel = path.lower().strip().endswith((".xlsx", ".xls"))
        if is_excel:
            print(f"DEBUG: Attempting to convert Excel (is_excel=True): {path}")
            try:
                if logger: logger(f"Converting Excel {os.path.basename(path)} to CSV for Gemini compatibility...")
                # read_only=True is faster and safer for some "invalid XML" cases
                wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
                ws = wb.active
                
                # Create a temporary CSV file
                fd, temp_path = tempfile.mkstemp(suffix=".csv")
                with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    for row in ws.iter_rows(values_only=True):
                        # Filter out empty rows to keep it lean
                        if any(cell is not None for cell in row):
                            writer.writerow(row)
                
                path = temp_path
                temp_csv = temp_path
                mime_type = "text/csv"
                if logger: logger(f"Converted to temporary CSV: {os.path.basename(path)}")
            except Exception as e:
                err_msg = f"Standard Excel conversion failed ({e}). Attempting Emergency Recovery Mode..."
                print(f"DEBUG: {err_msg}")
                if logger: logger(err_msg)
                
                try:
                    # Last resort: Raw XML extraction
                    # Generate a new temp path because the previous try block might have failed before creating it
                    fd, temp_path = tempfile.mkstemp(suffix=".csv")
                    os.close(fd)
                    
                    self._emergency_excel_to_csv(path, temp_path)
                    
                    path = temp_path
                    temp_csv = temp_path
                    mime_type = "text/csv"
                    if logger: logger("Emergency Recovery SUCCESS: Raw text extracted from Excel.")
                except Exception as ex:
                    final_err = f"Excel conversion completely FAILED: {ex}. (Tip: Please save as CSV manually.)"
                    print(f"DEBUG: {final_err}")
                    if logger: logger(final_err)
                    raise Exception(final_err)

        msg = f"Uploading file: {os.path.basename(original_path)}..."
        print(msg)
        if logger: logger(msg)
        
        # Robust MIME Detection
        if not mime_type:
            # ... existing mime logic ...
            mime_type, _ = mimetypes.guess_type(path)
            if not mime_type:
                # Common insurance file types fallbacks
                if path.lower().endswith('.pdf'): mime_type = 'application/pdf'
                elif path.lower().endswith('.xlsx'): mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                elif path.lower().endswith('.csv'): mime_type = 'text/csv'
                else: mime_type = 'application/octet-stream' # Last resort
            if logger: logger(f"Detected MIME type: {mime_type}")

        try:
            file_ref = genai.upload_file(path, mime_type=mime_type)
            # ... existing wait logic ...
            # implement active wait
            msg = f"Waiting for file {file_ref.name} to process..."
            print(msg)
            if logger: logger(msg)
            
            while file_ref.state.name == "PROCESSING":
                time.sleep(2)
                file_ref = genai.get_file(file_ref.name)
                if logger: logger(f"Processing... ({file_ref.state.name})")
            
            if file_ref.state.name != "ACTIVE":
                if logger: logger(f"Error: File failed with state {file_ref.state.name}")
                raise Exception(f"File {file_ref.name} failed to process. State: {file_ref.state.name}")
                
            if logger: logger(f"File {file_ref.name} is ready.")
            return file_ref
        finally:
            # Cleanup temporary CSV if created
            if temp_csv and os.path.exists(temp_csv):
                try:
                    os.remove(temp_csv)
                except:
                    pass

    def _emergency_excel_to_csv(self, xlsx_path, output_csv_path):
        """Emergency Raw XML parsing of Excel files when standard libraries fail."""
        try:
            with zipfile.ZipFile(xlsx_path, 'r') as z:
                # 1. Get Shared Strings
                strings = []
                try:
                    with z.open('xl/sharedStrings.xml') as f:
                        tree = ET.parse(f)
                        for node in tree.iter():
                            if node.tag.endswith('t'):
                                strings.append(node.text or "")
                except: pass

                # 2. Get Sheet1 data
                # We try to find any worksheet
                sheet_files = [n for n in z.namelist() if 'xl/worksheets/sheet' in n]
                if not sheet_files: raise Exception("No worksheets found in Excel zip")
                
                rows = []
                with z.open(sheet_files[0]) as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    # Namespaces are tricky in Excel XML
                    ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    
                    for row_node in root.findall('.//main:row', ns):
                        cols = []
                        for cell_node in row_node.findall('main:c', ns):
                            val_node = cell_node.find('main:v', ns)
                            if val_node is not None:
                                val = val_node.text
                                t = cell_node.get('t')
                                if t == 's': # Shared String
                                    idx = int(val)
                                    val = strings[idx] if idx < len(strings) else val
                                cols.append(val)
                            else:
                                cols.append("")
                        rows.append(cols)

                with open(output_csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerows(rows)
        except Exception as e:
            raise Exception(f"Emergency Recovery FAILED: {str(e)}")

    def extract_data(self, target_pdf_path, reference_paths=None, logger=None):
        """
        Extracts insurance data using Gemini RAG.
        
        Args:
            target_pdf_path (str): Path to the new PDF policy file (Input).
            reference_paths (list of str, optional): List of paths to reference files (Old PDFs, Excel Rules).
            logger (callable, optional): Callback for log messages.
        """
        uploaded_files = []
        try:
            # 1. Upload Target PDF
            if logger: logger(f"Step 1/4: Uploading Target PDF ({os.path.basename(target_pdf_path)})...")
            target_ref = self.upload_file(target_pdf_path, mime_type="application/pdf", logger=logger)
            uploaded_files.append(target_ref)

            # 2. Upload Reference Files
            files_context = [] # All files passed to generate_content
            
            # Add references first (context)
            if reference_paths:
                if logger: logger(f"Step 2/4: Uploading {len(reference_paths)} Reference Files...")
                for idx, path in enumerate(reference_paths):
                    mime = None 
                    if path.lower().endswith(".pdf"):
                        mime = "application/pdf"
                    # Excel and others handled by upload_file or auto-detection
                    
                    if logger: logger(f"  - Uploading Ref {idx+1}: {os.path.basename(path)}...")
                    ref_file = self.upload_file(path, mime_type=mime, logger=logger)
                    uploaded_files.append(ref_file)
                    files_context.append(ref_file)
            
            # Add target file last
            files_context.append(target_ref)

            # 3. Construct Prompt
            if logger: logger("Step 3/4: Generating RAG Prompt...")
            prompt = f"""
            You are an expert Insurance Policy Analyst.
            
            **Context**:
            The user has provided several reference files (Old Policies, Rule Excel, etc.) which are attached before the final document.
            These references define how to interpret rules, map terms to codes, and handle specific clauses.
            
            **Task**:
            Analyze the FINAL attached document (The "Target" Insurance Policy PDF).
            **IMPORTANT**: This is a direct PDF input. You must utilize your **multimodal capabilities** to read not just the text, but also **tables, charts, and the visual layout**.
            Many insurance details (like coverage limits or disease codes) are presented in finding grids or tables. 
            
            Using the patterns, logic, and codes found in the Reference files, extract the specific information from the Target Policy.
            
            Please extract the following fields and return them in a valid JSON format.
            Do not include Markdown formatting (```json ... ```). Just return the raw JSON string.
            
            **Ideally, for each extracted field, cite the page number and text from the Target PDF where you found the information.** 
            However, to keep the JSON structure flat for the UI, please provide a separate "citations" object or just valid fields. 
            Actually, let's add a "source_evidence" field that summarizes where the key data came from.
 
            Fields to extract:
            1. benefitType (default: "ZU5042000")
            2. benefitName (The name of the special clause/benefit, typically found in the title header)
            3. node ("수술" or "진단" based on context)
            4. accidentType (default: "=질병")
            5. coverageCode (default: "ZD3529010")
            6. diagnosisCode (The disease codes found. Look for tables listing '분류번호' or 'Code'. If inferred, state "Inferred from rule")
            7. surgeryCode (Any surgery specific code or name)
            8. ediCode (EDI codes - often found in tables mapping surgeries to codes)
            9. reduction (Reduction conditions - look for '50%' or '1년' columns in tables)
            10. limit (Payment limit)
            11. hospital (Hospital types mentioned)
            12. formula (Calculation formula)
            13. source_evidence (String: Cite the page number(s) and a brief quote/description of the table/visual where the data was found. e.g. "Page 5 Table 2 row 3...")
 
            If a value is not found in the target policy, infer it from the reference rules if applicable (e.g. standard codes), otherwise use an empty string "".
            For 'diagnosisCode', if there is a list of diseases, format it as a single string.
            """

            # 4. Generate Content
            model_name = self.model.model_name.split('/')[-1] if self.model else "Gemini"
            if logger: logger(f"Step 4/4: Asking {model_name} to extract data...")
            response = self.model.generate_content([prompt] + files_context)
            
            if logger: logger("Analysis Complete. Parsing result...")
            
            # 5. Parse JSON
            raw_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(raw_text)

        except Exception as e:
            print(f"Gemini Extraction Error: {e}")
            return {"error": str(e)}
        finally:
            # optional: delete files to clean up? Or keep them for session? 
            # For this POC, we can leave them or delete them. Let's start with cleaning up to save storage usage.
            for f in uploaded_files:
                try:
                    genai.delete_file(f.name)
                except:
                    pass


