
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from logic.code_mapper import DiagnosisMapper
import os
import shutil
import tempfile
import uvicorn
from starlette.concurrency import run_in_threadpool
import datetime

from typing import List


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Mapper
mapper = None
log_buffer = []

def add_log(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    log_buffer.append(log_entry)

@app.post("/api/configure")
async def configure(api_key: str = Form(...)):
    global mapper
    try:
        mapper = DiagnosisMapper(api_key)
        return {"status": "configured"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def get_logs():
    return {"logs": log_buffer}

@app.post("/api/analyze_step3")
async def analyze_step3(
    target_pdf: UploadFile = File(...),
    target_excel: UploadFile = File(...),
    mapping_files: List[UploadFile] = File(...),
    ref_files: List[UploadFile] = File(default=[])
):
    global mapper
    if not mapper:
        raise HTTPException(status_code=400, detail="API Key not configured")

    global log_buffer
    log_buffer = []
    add_log(f"Starting Unified Analysis (9 Attributes) with {len(mapping_files)} mapping tables and {len(ref_files)} references...")

    # Create unique temp dir
    request_dir = tempfile.mkdtemp(prefix="poc3_req_")
    
    def save(uf):
        path = os.path.join(request_dir, os.path.basename(uf.filename))
        with open(path, "wb") as f:
            shutil.copyfileobj(uf.file, f)
        return path

    try:
        t_pdf = save(target_pdf)
        t_exc = save(target_excel)
        
        saved_maps = [save(mf) for mf in mapping_files]
        saved_refs = [save(rf) for rf in ref_files]
        
        add_log(f"Inputs saved: PDF, Excel, {len(saved_maps)} Mapping Files")
        
        # Call the unified process method
        result = await run_in_threadpool(
            mapper.process, 
            t_pdf, 
            t_exc, 
            saved_maps, # Pass as list
            ref_files=saved_refs,
            logger=add_log
        )
        
        if "error" in result:
            add_log(f"Analysis failed: {result['error']}")
            raise HTTPException(status_code=500, detail=result['error'])
            
        add_log("Analysis Completed.")
        return result

    except Exception as e:
        add_log(f"Server Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(request_dir):
            shutil.rmtree(request_dir)

@app.get("/api/download")
async def download(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        filename = "diagnosis_coded_results.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif ext == ".zip":
        filename = "mapping_logics.zip"
        media_type = "application/zip"
    else:
        filename = "mapping_logic.txt"
        media_type = "text/plain"
    
    return FileResponse(path, filename=filename, media_type=media_type)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8002, reload=True)
