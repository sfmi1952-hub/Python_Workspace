from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import shutil
import os
import uvicorn
import json
from typing import List, Optional
import tempfile

# Helper for Logic Imports
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from logic.gemini_client import GeminiClient

app = FastAPI()

# Enable CORS for React Dev Server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For creating the UI, we'll allow all. Lock down later if needed.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Client Instance
gemini_client = GeminiClient()

class ConfigureRequest(BaseModel):
    api_key: str

@app.post("/api/configure")
async def configure_api(request: ConfigureRequest):
    """Configures the Gemini Client with the provided API Key."""
    if not request.api_key:
        raise HTTPException(status_code=400, detail="API Key is required")
    
    try:
        gemini_client.configure(request.api_key)
        return {"status": "success", "message": "API Key configured successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze")
async def analyze_file(file: UploadFile = File(...)):
    """Accepts a file, saves it temporarily, and runs Gemini extraction."""
    if not gemini_client.api_key:
        raise HTTPException(status_code=400, detail="API Key not configured. Please call /api/configure first.")
    
    # Save Uploaded File
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        # Run Extraction
        # We assume no reference files for this simple endpoint for now, 
        # or we could add a multipart field for multiple files later.
        result = gemini_client.extract_data(tmp_path, logger=print)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.post("/api/chat")
async def chat_interaction(prompt: str = Form(...), context: str = Form(None)):
    """Simple chat endpoint. For a real app, we'd want a session-based history."""
    if not gemini_client.model:
         raise HTTPException(status_code=400, detail="Gemini model not ready.")
    
    try:
        # Basic one-off chat for now.
        # Construct a prompt with context
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nUser Question:\n{prompt}"
            
        response = gemini_client.model.generate_content(full_prompt)
        return {"response": response.text}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

# Placeholder for serving static files (React build)
# app.mount("/", StaticFiles(directory="web_ui/dist", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
