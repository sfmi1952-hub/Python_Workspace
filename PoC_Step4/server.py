
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from logic.risk_mapper import RiskMapper
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

# Global Mappers
risk_mapper = None
log_buffer = []

def add_log(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    log_buffer.append(log_entry)

@app.post("/api/configure")
async def configure(api_key: str = Form(...)):
    global risk_mapper
    try:
        risk_mapper = RiskMapper(api_key)
        return {"status": "configured"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def get_logs():
    return {"logs": log_buffer}



@app.post("/api/analyze_step4")
async def analyze_step4(
    target_docx: UploadFile = File(...),
    target_csv: UploadFile = File(...),
    mapping_files: List[UploadFile] = File(...),
    ref_files: List[UploadFile] = File(default=[])
):
    global risk_mapper
    if not risk_mapper:
        raise HTTPException(status_code=400, detail="API Key not configured")

    global log_buffer
    log_buffer = []
    add_log(f"Starting Risk Inference (Step 4) with {len(ref_files)} reference files...")

    # Create unique temp dir
    request_dir = tempfile.mkdtemp(prefix="poc4_req_")
    
    def save(uf):
        # Handle duplicate filenames if necessary, but assuming unique for now
        path = os.path.join(request_dir, os.path.basename(uf.filename))
        with open(path, "wb") as f:
            shutil.copyfileobj(uf.file, f)
        return path

    try:
        t_docx = save(target_docx)
        t_csv = save(target_csv)
        
        saved_maps = [save(mf) for mf in mapping_files]
        saved_refs = [save(rf) for rf in ref_files]
        
        add_log(f"Inputs saved: Target DOCX, CSV, {len(saved_maps)} Mapping Files, {len(saved_refs)} Ref Files")
        
        result = await run_in_threadpool(
            risk_mapper.process, 
            t_docx, 
            t_csv, 
            saved_maps, 
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
        # Cleanup is handled by RiskMapper mostly, but we should clean request_dir
        # RiskMapper writes to data/result, so request_dir input files can be deleted.
        if os.path.exists(request_dir):
            try:
                shutil.rmtree(request_dir)
            except: pass

@app.get("/api/download")
async def download(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    
    ext = os.path.splitext(path)[1].lower()
    filename = os.path.basename(path) # default
    
    if ext == ".xlsx":
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif ext == ".csv":
        media_type = "text/csv"
    elif ext == ".zip":
        media_type = "application/zip"
    else:
        media_type = "text/plain"
    
    return FileResponse(path, filename=filename, media_type=media_type)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8002, reload=True)
