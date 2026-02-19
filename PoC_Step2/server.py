
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

@app.post("/api/analyze_step2")
async def analyze_step2(
    target_pdf: UploadFile = File(...),
    target_excel: UploadFile = File(...),
    code_mapping: UploadFile = File(...),
    ref_files: List[UploadFile] = File(default=[])
):
    global mapper
    if not mapper:
        raise HTTPException(status_code=400, detail="API Key not configured")

    global log_buffer
    log_buffer = []
    add_log(f"Starting Step 2 Analysis (Diagnosis Coding) with {len(ref_files)} reference files...")

    # Create unique temp dir
    request_dir = tempfile.mkdtemp(prefix="poc2_req_")
    
    def save(uf):
        path = os.path.join(request_dir, os.path.basename(uf.filename))
        with open(path, "wb") as f:
            shutil.copyfileobj(uf.file, f)
        return path

    try:
        t_pdf = save(target_pdf)
        t_exc = save(target_excel)
        c_map = save(code_mapping)
        
        saved_ref_paths = []
        for rf in ref_files:
            saved_ref_paths.append(save(rf))
        
        add_log(f"Inputs saved: {os.path.basename(t_pdf)}, {os.path.basename(t_exc)}, {os.path.basename(c_map)}")
        if saved_ref_paths:
            add_log(f"Reference files saved: {len(saved_ref_paths)} items")
        
        result = await run_in_threadpool(
            mapper.process, 
            t_pdf, 
            t_exc, 
            c_map, 
            ref_files=saved_ref_paths,
            logger=add_log
        )
        
        if "error" in result:
            add_log(f"Analysis failed: {result['error']}")
            raise HTTPException(status_code=500, detail=result['error'])
            
        add_log("Step 2 Analysis Completed.")
        return result

    except Exception as e:
        add_log(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(request_dir):
            shutil.rmtree(request_dir)

@app.get("/api/download")
async def download(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    
    ext = os.path.splitext(path)[1].lower()
    filename = "diagnosis_coded_results.xlsx" if ext == ".xlsx" else "mapping_logic.txt"
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if ext == ".xlsx" else "text/plain"
    
    return FileResponse(path, filename=filename, media_type=media_type)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8002, reload=True)
