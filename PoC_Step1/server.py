from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from logic.mapper import BenefitMapper
import os
import shutil
import tempfile
import uvicorn
from typing import List

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Mapper (Lazy init)
mapper = None

@app.post("/api/configure")
async def configure(api_key: str = Form(...)):
    global mapper
    try:
        mapper = BenefitMapper(api_key)
        return {"status": "configured"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from starlette.concurrency import run_in_threadpool
import datetime

# Global Log Buffer
log_buffer = []

def add_log(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry) # Also print to console
    log_buffer.append(log_entry)

@app.get("/api/logs")
async def get_logs():
    return {"logs": log_buffer}

@app.post("/api/logs/clear")
async def clear_logs():
    global log_buffer
    log_buffer = []
    return {"status": "cleared"}

@app.post("/api/analyze")
async def analyze(
    target_pdf: UploadFile = File(...),
    target_excel: UploadFile = File(...),
    ref_files: List[UploadFile] = File(default=[])
):
    global mapper
    if not mapper:
        raise HTTPException(status_code=400, detail="API Key not configured")

    # Clear logs at start of new analysis
    global log_buffer
    log_buffer = []
    add_log("Starting new analysis request...")

    # Create a unique temp directory for this request to preserve filenames
    request_dir = tempfile.mkdtemp(prefix="poc_req_")
    add_log(f"Created temp directory: {request_dir}")

    def save(uf):
        # Use original filename to allow grouping in mapper.py
        original_name = os.path.basename(uf.filename)
        save_path = os.path.join(request_dir, original_name)
        
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(uf.file, buffer)
            
        return save_path

    try:
        t_pdf = save(target_pdf)
        t_exc = save(target_excel)
        refs = [save(r) for r in ref_files]
        
        add_log(f"Files saved. PDF: {os.path.basename(target_pdf.filename)}, Excel: {os.path.basename(target_excel.filename)}")
        add_log(f"Reference files count: {len(refs)}")
        
        # Run synchronous mapper.process in a threadpool to avoid blocking the event loop
        # This allows /api/logs to be called while this is running
        result = await run_in_threadpool(mapper.process, t_pdf, t_exc, refs, logger=add_log)
        
        if "error" in result:
            add_log(f"Analysis failed: {result['error']}")
            raise HTTPException(status_code=500, detail=result['error'])
            
        add_log("Analysis completed successfully.")
        return result

    except Exception as e:
        print(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup unique request directory
        if os.path.exists(request_dir):
            try: shutil.rmtree(request_dir)
            except: pass

@app.get("/api/download")
async def download(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename="mapped_results.xlsx")

if __name__ == "__main__":
    # Port 8001 to avoid conflict
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=True)
