"""
Facebook URL Search Automation Tool
Web-based automation tool powered by OpenAI API
"""
import os
import asyncio
import csv
import json
from datetime import datetime
from typing import List, Dict
from io import StringIO, BytesIO

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from openai import OpenAI
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
load_dotenv()

# Initialize FastAPI
app = FastAPI(title="Facebook URL Search Tool")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global storage for processing status (in production, use Redis or database)
processing_status = {}

# OpenAI API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️  WARNING: OPENAI_API_KEY not set. Please set it in environment variables.")

client = OpenAI(api_key=OPENAI_API_KEY)

class BusinessRecord(BaseModel):
    business_name: str
    location: str


class ProcessedRecord(BaseModel):
    business_name: str
    location: str
    facebook_url: str
    type: str
    confidence: float
    notes: str


async def search_facebook_page(business_name: str, location: str) -> Dict:
    """
    Use OpenAI API with Web Search to find Facebook business page or group
    Returns structured data with URL, type, confidence, and notes
    """
    
    prompt = f"""Use web search to find the official Facebook business page for: {business_name}, {location}

Instructions:
1. Get the official Facebook page for this business
2. If no official Facebook page exists, get an unofficial Facebook page for the same search query
3. If no unofficial Facebook page exists, get the most relevant Facebook group for the same search query
4. Output should be the www.facebook.com URL

Return your findings as a JSON object with these exact fields:
{{
  "facebook_url": "the most relevant Facebook URL found (e.g., https://www.facebook.com/BusinessName/)",
  "type": "page or group - determine from URL structure (facebook.com/name/ is page, facebook.com/groups/ is group, facebook.com/p/ is also page)",
  "confidence": a number between 0.0 and 1.0 based on name/location match quality,
  "notes": "brief explanation like 'Official verified page in [location]' or 'Best match: [description]' or 'Alternative group found'"
}}

Important rules:
- MUST use web search to find current, accurate Facebook URLs
- Prefer official business Pages over Groups
- Verify the location matches or is very close
- If uncertain about the match, provide your best guess in 'notes' or mention alternatives
- If no good match found at all, set confidence to 0.0 and facebook_url to "Not found"
- Return ONLY valid JSON, no other text before or after"""

    try:
        # Using GPT-4o with web search capabilities
        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-4o",  # gpt-4o has web search integration
            tools=[{
                "type": "web_search_preview_2025_03_11",
            }],
            input=prompt,
        )
        
        # Parse the response
        content = response.output_text.strip()
        
        # Try to extract JSON if wrapped in markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        
        # Validate required fields
        required_fields = ["facebook_url", "type", "confidence", "notes"]
        for field in required_fields:
            if field not in result:
                result[field] = "N/A" if field != "confidence" else 0.0
        
        # Ensure confidence is float
        result["confidence"] = float(result["confidence"])
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error for {business_name}: {e}")
        return {
            "facebook_url": "Error - Invalid response",
            "type": "error",
            "confidence": 0.0,
            "notes": f"Failed to parse API response"
        }
    except Exception as e:
        print(f"Error searching for {business_name}: {e}")
        return {
            "facebook_url": "Error",
            "type": "error",
            "confidence": 0.0,
            "notes": f"API error: {str(e)}"
        }


async def process_batch_with_rate_limit(records: List[Dict], task_id: str):
    """
    Process multiple records with rate limiting and progress tracking
    """
    results = []
    total = len(records)
    
    # Update initial status
    processing_status[task_id] = {
        "status": "processing",
        "progress": 0,
        "total": total,
        "results": []
    }
    
    # Process with concurrency control (max 5 concurrent requests)
    semaphore = asyncio.Semaphore(5)
    
    async def process_with_semaphore(record, index):
        async with semaphore:
            result = await search_facebook_page(
                record["business_name"],
                record["location"]
            )
            
            # Add original data to result
            result["business_name"] = record["business_name"]
            result["location"] = record["location"]
            
            # Update progress
            progress = ((index + 1) / total) * 100
            processing_status[task_id]["progress"] = progress
            
            # Add small delay to respect rate limits
            await asyncio.sleep(0.5)
            
            return result
    
    # Process all records
    tasks = [
        process_with_semaphore(record, i) 
        for i, record in enumerate(records)
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Update final status
    processing_status[task_id] = {
        "status": "completed",
        "progress": 100,
        "total": total,
        "results": results
    }
    
    return results


@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the main web interface"""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Facebook URL Search Tool</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
        }
        
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 32px;
        }
        
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 16px;
        }
        
        .upload-section {
            border: 3px dashed #667eea;
            border-radius: 15px;
            padding: 40px;
            text-align: center;
            margin-bottom: 30px;
            background: #f8f9ff;
            transition: all 0.3s;
        }
        
        .upload-section:hover {
            border-color: #764ba2;
            background: #f0f1ff;
        }
        
        .upload-section input[type="file"] {
            display: none;
        }
        
        .upload-label {
            display: inline-block;
            padding: 15px 40px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 50px;
            cursor: pointer;
            font-weight: 600;
            transition: transform 0.2s;
        }
        
        .upload-label:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        
        .file-info {
            margin-top: 15px;
            color: #666;
            font-size: 14px;
        }
        
        .btn {
            padding: 15px 40px;
            border: none;
            border-radius: 50px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            margin: 10px;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .btn-primary:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
        }
        
        .btn-success:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(56, 239, 125, 0.4);
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .progress-section {
            display: none;
            margin-top: 30px;
        }
        
        .progress-bar-container {
            width: 100%;
            height: 30px;
            background: #e0e0e0;
            border-radius: 15px;
            overflow: hidden;
            margin: 20px 0;
        }
        
        .progress-bar {
            height: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            width: 0%;
            transition: width 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 600;
        }
        
        .status-text {
            color: #666;
            text-align: center;
            margin: 10px 0;
        }
        
        .results-section {
            display: none;
            margin-top: 30px;
            padding: 20px;
            background: #f8f9ff;
            border-radius: 15px;
        }
        
        .result-item {
            background: white;
            padding: 15px;
            margin: 10px 0;
            border-radius: 10px;
            border-left: 4px solid #667eea;
        }
        
        .result-item strong {
            color: #333;
        }
        
        .confidence-high { border-left-color: #38ef7d; }
        .confidence-medium { border-left-color: #ffd93d; }
        .confidence-low { border-left-color: #ff6b6b; }
        
        .instructions {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        
        .instructions h3 {
            color: #856404;
            margin-bottom: 10px;
        }
        
        .instructions ul {
            margin-left: 20px;
            color: #856404;
        }
        
        .instructions li {
            margin: 5px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Facebook URL Search Tool</h1>
        <p class="subtitle">Powered by OpenAI API - Find Facebook business pages automatically</p>
        
        <div class="instructions">
            <h3>📋 Instructions:</h3>
            <ul>
                <li>Upload a CSV or Excel file with two columns: <strong>Business Name</strong> and <strong>Location</strong></li>
                <li>The system will search for official Facebook pages (or groups if not available)</li>
                <li>Download the results as a CSV with URL, Type, Confidence, and Notes</li>
            </ul>
        </div>
        
        <div class="upload-section">
            <input type="file" id="fileInput" accept=".csv,.xlsx,.xls">
            <label for="fileInput" class="upload-label">📁 Choose File</label>
            <div class="file-info" id="fileInfo">No file selected</div>
        </div>
        
        <div style="text-align: center;">
            <button class="btn btn-primary" id="processBtn" onclick="processFile()" disabled>
                🚀 Start Processing
            </button>
        </div>
        
        <div class="progress-section" id="progressSection">
            <div class="status-text" id="statusText">Initializing...</div>
            <div class="progress-bar-container">
                <div class="progress-bar" id="progressBar">0%</div>
            </div>
        </div>
        
        <div class="results-section" id="resultsSection">
            <h3>✅ Processing Complete!</h3>
            <p class="status-text" id="resultsSummary"></p>
            <button class="btn btn-success" onclick="downloadResults()">
                📥 Download Results CSV
            </button>
            <div id="resultsPreview"></div>
        </div>
    </div>
    
    <script>
        let selectedFile = null;
        let currentTaskId = null;
        
        document.getElementById('fileInput').addEventListener('change', function(e) {
            selectedFile = e.target.files[0];
            if (selectedFile) {
                document.getElementById('fileInfo').textContent = `Selected: ${selectedFile.name}`;
                document.getElementById('processBtn').disabled = false;
            }
        });
        
        async function processFile() {
            if (!selectedFile) return;
            
            const formData = new FormData();
            formData.append('file', selectedFile);
            
            document.getElementById('processBtn').disabled = true;
            document.getElementById('progressSection').style.display = 'block';
            document.getElementById('resultsSection').style.display = 'none';
            
            try {
                // Upload and start processing
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                currentTaskId = data.task_id;
                
                // Poll for progress
                pollProgress();
                
            } catch (error) {
                alert('Error uploading file: ' + error.message);
                document.getElementById('processBtn').disabled = false;
            }
        }
        
        async function pollProgress() {
            const interval = setInterval(async () => {
                try {
                    const response = await fetch(`/status/${currentTaskId}`);
                    const data = await response.json();
                    
                    const progress = Math.round(data.progress);
                    document.getElementById('progressBar').style.width = progress + '%';
                    document.getElementById('progressBar').textContent = progress + '%';
                    document.getElementById('statusText').textContent = 
                        `Processing: ${Math.round(data.progress * data.total / 100)} of ${data.total} records`;
                    
                    if (data.status === 'completed') {
                        clearInterval(interval);
                        showResults(data);
                    }
                    
                } catch (error) {
                    clearInterval(interval);
                    alert('Error checking status: ' + error.message);
                }
            }, 1000);
        }
        
        function showResults(data) {
            document.getElementById('progressSection').style.display = 'none';
            document.getElementById('resultsSection').style.display = 'block';
            document.getElementById('resultsSummary').textContent = 
                `Processed ${data.total} records successfully!`;
            
            // Show preview of first few results
            const preview = document.getElementById('resultsPreview');
            preview.innerHTML = '<h4 style="margin-top: 20px;">Preview (first 5 results):</h4>';
            
            data.results.slice(0, 5).forEach(result => {
                const confidenceClass = result.confidence >= 0.7 ? 'confidence-high' : 
                                       result.confidence >= 0.4 ? 'confidence-medium' : 'confidence-low';
                
                preview.innerHTML += `
                    <div class="result-item ${confidenceClass}">
                        <strong>${result.business_name}</strong> - ${result.location}<br>
                        <small>URL: ${result.facebook_url} | Type: ${result.type} | Confidence: ${result.confidence}</small><br>
                        <small>Notes: ${result.notes}</small>
                    </div>
                `;
            });
        }
        
        async function downloadResults() {
            window.location.href = `/download/${currentTaskId}`;
        }
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@app.post("/upload")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload CSV/Excel file and start processing
    """
    try:
        # Read file content
        content = await file.read()
        
        # Determine file type and parse
        if file.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(content))
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(BytesIO(content))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV or Excel file.")
        
        # Validate columns (case insensitive)
        df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]
        
        required_cols = ['business_name', 'location']
        if not all(col in df.columns for col in required_cols):
            raise HTTPException(
                status_code=400, 
                detail=f"File must contain columns: Business Name, Location. Found: {list(df.columns)}"
            )
        
        # Convert to list of dicts
        records = df[required_cols].to_dict('records')
        
        # Generate task ID
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Start background processing
        background_tasks.add_task(process_batch_with_rate_limit, records, task_id)
        
        return {"task_id": task_id, "total_records": len(records)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@app.get("/status/{task_id}")
async def get_status(task_id: str):
    """
    Get processing status for a task
    """
    if task_id not in processing_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return processing_status[task_id]


@app.get("/download/{task_id}")
async def download_results(task_id: str):
    """
    Download results as CSV
    """
    if task_id not in processing_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = processing_status[task_id]
    
    if status["status"] != "completed":
        raise HTTPException(status_code=400, detail="Processing not completed yet")
    
    # Create CSV from results
    results = status["results"]
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Reorder columns
    columns_order = ["business_name", "location", "facebook_url", "type", "confidence", "notes"]
    df = df[columns_order]
    
    # Rename columns for output
    df.columns = ["Business Name", "Location", "Facebook URL", "Type", "Confidence", "Notes"]
    
    # Save to CSV
    output_file = f"results_{task_id}.csv"
    df.to_csv(output_file, index=False)
    
    return FileResponse(
        output_file,
        media_type="text/csv",
        filename=f"facebook_urls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "openai_api_configured": bool(OPENAI_API_KEY)
    }


if __name__ == "__main__":
    print("🚀 Starting Facebook URL Search Tool...")
    print("📍 Server will be available at: http://localhost:8000")
    print("⚠️  Make sure OPENAI_API_KEY is set in environment variables")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

