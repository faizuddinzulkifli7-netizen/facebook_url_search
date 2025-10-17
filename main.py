"""
Facebook URL Search Automation Tool
Web-based automation tool powered by Google Custom Search JSON API
"""
import os
import asyncio
import csv
import json
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from io import StringIO, BytesIO
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openai import AsyncOpenAI

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

# Mount static files for favicon
app.mount("/static", StaticFiles(directory="Favico"), name="static")

# Global storage for processing status (in production, use Redis or database)
processing_status = {}

# API Configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not GOOGLE_API_KEY:
    print("WARNING: GOOGLE_API_KEY not set. Please set it in environment variables.")
if not GOOGLE_CSE_ID:
    print("WARNING: GOOGLE_CSE_ID not set. Please set it in environment variables.")
if not OPENAI_API_KEY:
    print("WARNING: OPENAI_API_KEY not set. Please set it in environment variables.")

# Google Custom Search Service
try:
    google_service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY) if GOOGLE_API_KEY else None
except Exception as e:
    print(f"WARNING: Error initializing Google Search API: {e}")
    google_service = None

# OpenAI Client for AI-powered filtering
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


class SearchConfig(BaseModel):
    google_property: str = "google.com"  # google.com, google.it, google.co.uk, etc.
    language: str = "en"  # en, it, fr, es, etc.


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


def clean_json_response(text: str) -> str:
    """
    Clean AI response by removing markdown code fences if present
    """
    text = text.strip()
    
    # Remove markdown code fences
    if text.startswith('```'):
        # Remove opening fence (```json or ```JSON or just ```)
        lines = text.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]  # Remove first line with ```
        
        # Remove closing fence
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]  # Remove last line with ```
        
        text = '\n'.join(lines).strip()
    
    return text


async def ai_filter_and_select_url(
    search_results: List[Dict],
    business_name: str,
    location: str,
    openai_key: str
) -> Dict:
    """
    Use AI agent to intelligently filter and select the best Facebook URL
    Returns the best match with reasoning
    Requires OpenAI API key
    """
    
    # Use provided API key to create client
    try:
        client = AsyncOpenAI(api_key=openai_key)
    except Exception as e:
        # If client creation fails, return error
        return {
            "facebook_url": "Error",
            "type": "error",
            "confidence": 0.0,
            "notes": f"Failed to initialize OpenAI client: {str(e)}"
        }
    
    # Prepare search results for AI analysis
    results_text = []
    for i, result in enumerate(search_results, 1):
        results_text.append(f"""
Result {i}:
URL: {result['url']}
Title: {result.get('title', 'N/A')}
Description: {result.get('snippet', 'N/A')}
""")
    
    results_str = "\n".join(results_text)
    
    prompt = f"""You are an expert at analyzing Facebook search results to find official business pages.

BUSINESS NAME: {business_name}
LOCATION: {location}

SEARCH RESULTS FROM GOOGLE (site:facebook.com):
{results_str}

YOUR TASK:
Analyze these Facebook URLs and select the BEST official Facebook business page for this business.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 FACEBOOK URL CLASSIFICATION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏢 1. BUSINESS / OFFICIAL PAGES (BEST - Target these!)
   
   ✅ URL Patterns:
   • Clean vanity: facebook.com/TennisClubOvada/
   • Modern /p/: facebook.com/p/Tennis-Club-Le-Colline-61566371468729/
   • Legacy: facebook.com/pages/Tennis-Club/123456789012345/
   • Mobile: m.facebook.com/TennisClubOvada/
   
   ✅ Detection Logic:
   • Does NOT contain /groups/
   • Does NOT contain profile.php?id=
   • May start with /p/ OR has business-like name
   • Type: "page"

👥 2. GROUPS (Acceptable if no business page found)
   
   ✅ URL Patterns:
   • Named: facebook.com/groups/miamitennisplayers/
   • Numeric: facebook.com/groups/123456789012345/
   • Mobile: m.facebook.com/groups/tennisinbali/
   
   ✅ Detection Logic:
   • Contains /groups/ (case-insensitive)
   • Type: "group"

👤 3. PERSONAL PROFILES (AVOID - These are NOT businesses!)
   
   ✅ URL Patterns:
   • Numeric ID: facebook.com/profile.php?id=1234567890
   • Vanity profile: facebook.com/john.smith.123/
   
   ✅ Detection Logic:
   • Contains profile.php?id=
   • OR looks like a personal name (lowercase words separated by dots)
   • Type: "other"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚫 BAD URL PATHS TO AVOID
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

These are NOT the main business page - they are sub-pages:
❌ /about, /posts, /mentions, /reviews, /photos, /media, /reel, /videos
❌ /events, /live_videos, /followers, /music, /map, /sports, /movies, /tv
❌ /books, /likes, /reviews_given

ONLY select the main page URL (clean URL without these paths).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 SELECTION PRIORITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ✅ FIRST: Look for clean BUSINESS PAGE (facebook.com/BusinessName/ or /p/...)
2. ✅ SECOND: If no page found, look for GROUP (facebook.com/groups/...)
3. ❌ NEVER: Select personal profiles (profile.php or personal names)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 NAME MATCHING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Match the business name "{business_name}" with:
• URL slug (e.g., /TennisClubOvada/ matches "Tennis Club Ovada")
• Page title in search results
• Description mentioning the business
• Location "{location}" mentioned in title/description

Consider:
• Abbreviations (e.g., "NYC" for "New York City")
• Variations (e.g., "Starbucks" vs "Starbucks Coffee")
• Word order changes
• Spaces vs no spaces (e.g., "TennisClub" vs "Tennis Club")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📤 RESPONSE FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return ONLY valid JSON (no markdown formatting):

{{
  "facebook_url": "the best URL or 'Not found'",
  "type": "page" or "group" or "other" or "not_found",
  "confidence": 0.0 to 1.0,
  "reasoning": "Explain: 1) What type of URL is this (page/group/profile)? 2) Why it matches the business name? 3) Why you chose this over other results?"
}}

Return ONLY the JSON object."""

    try:
        response = await client.responses.create(
            model="gpt-4o",  # Cost-effective and fast
            input=prompt,
            temperature=0.1,  # Lower temperature for more consistent results
        )
        
        # Clean the response to remove markdown code fences if present
        cleaned_response = clean_json_response(response.output_text)
        print(f"AI Response (cleaned): {cleaned_response}")
        result = json.loads(cleaned_response)
        
        # Validate and normalize the response
        return {
            "facebook_url": result.get("facebook_url", "Not found"),
            "type": result.get("type", "not_found"),
            "confidence": float(result.get("confidence", 0.0)),
            "notes": result.get("reasoning", "AI analysis completed")
        }
        
    except Exception as e:
        print(f"AI filtering error: {e}")
        # Fallback - return first result
        if search_results:
            first = search_results[0]
            return {
                "facebook_url": first['url'],
                "type": "unknown",
                "confidence": 0.5,
                "notes": f"AI error - returning first result: {first.get('title', '')}. Error: {str(e)}"
            }
        return {
            "facebook_url": "Not found",
            "type": "not_found",
            "confidence": 0.0,
            "notes": f"AI error: {str(e)}"
        }


def filter_facebook_urls(urls_data: List[Dict]) -> List[Dict]:
    """
    Simple filter: only keep URLs from facebook.com domain
    Returns list of Facebook URLs to feed to AI
    """
    facebook_urls = []
    
    for item in urls_data:
        url = item.get('url', '')
        
        # Check if it's a Facebook URL
        if 'facebook.com' in url.lower():
            facebook_urls.append({
                'url': url,
                'title': item.get('title', ''),
                'snippet': item.get('snippet', '')
            })
    
    return facebook_urls


async def search_facebook_page_google(
    business_name: str, 
    location: str,
    api_key: str,
    cse_id: str,
    openai_key: str,
    country_code: str = "us",
    language: str = "en",
    num_results: int = 20
) -> Dict:
    """
    Use Google Custom Search JSON API to find Facebook business page or group
    Returns structured data with URL, type, confidence, and notes
    Requires OpenAI API key for AI-powered filtering
    """
    
    try:
        # Build Google service with provided API key
        service = build("customsearch", "v1", developerKey=api_key)
    except Exception as e:
        return {
            "facebook_url": "Error",
            "type": "error",
            "confidence": 0.0,
            "notes": f"Failed to initialize Google Search API: {str(e)}"
        }
    
    try:
        # Build search query with site restriction
        search_query = f"site:facebook.com {business_name} {location}"
        
        # Execute search
        result = service.cse().list(
            q=search_query,
            cx=cse_id,
            num=min(num_results, 10),  # Google API allows max 10 per request
            gl=country_code,  # Country code
            lr=f"lang_{language}",  # Language
            safe='off'
        ).execute()
        
        # Extract search results
        items = result.get('items', [])
        
        if not items:
            # No results found
            return {
                "facebook_url": "Not found",
                "type": "not_found",
                "confidence": 0.0,
                "notes": f"No Facebook pages found for '{business_name}' in '{location}' (country: {country_code}, language: {language})"
            }
        
        # Prepare URLs data - just filter for facebook.com
        urls_data = []
        for item in items:
            urls_data.append({
                'url': item.get('link', ''),
                'title': item.get('title', ''),
                'snippet': item.get('snippet', '')
            })
        
        # Filter to only Facebook URLs
        facebook_urls = filter_facebook_urls(urls_data)
        
        if not facebook_urls:
            return {
                "facebook_url": "Not found",
                "type": "not_found",
                "confidence": 0.0,
                "notes": "No Facebook URLs found in search results"
            }
        
        # Use AI agent to analyze and select the best URL
        result = await ai_filter_and_select_url(facebook_urls, business_name, location, openai_key)
        
        return result
        
    except HttpError as e:
        error_details = json.loads(e.content.decode('utf-8'))
        error_message = error_details.get('error', {}).get('message', str(e))
        return {
            "facebook_url": "Error",
            "type": "error",
            "confidence": 0.0,
            "notes": f"Google API error: {error_message}"
        }
    except Exception as e:
        return {
            "facebook_url": "Error",
            "type": "error",
            "confidence": 0.0,
            "notes": f"Error: {str(e)}"
        }


async def process_batch_with_config(
    records: List[Dict], 
    task_id: str,
    api_key: str,
    cse_id: str,
    openai_key: str,
    country_code: str = "us",
    language: str = "en"
):
    """
    Process multiple records one by one sequentially with progress tracking
    Uses user-provided API credentials (all required)
    """
    results = []
    total = len(records)
    
    # Update initial status
    processing_status[task_id] = {
        "status": "processing",
        "progress": 0,
        "total": total,
        "results": [],
        "config": {
            "api_key": api_key[:10] + "...",  # Store partial key for reference
            "cse_id": cse_id[:10] + "...",     # Store partial ID for reference
            "country_code": country_code,
            "language": language
        }
    }
    
    # Process one by one
    for index, record in enumerate(records):
        print(f"Processing {index + 1}/{total}: {record['business_name']}")
        
        # Search for Facebook page with user credentials
        result = await search_facebook_page_google(
            record["business_name"],
            record["location"],
            api_key=api_key,
            cse_id=cse_id,
            openai_key=openai_key,
            country_code=country_code,
            language=language
        )
        
        # Add original data to result
        result["business_name"] = record["business_name"]
        result["location"] = record["location"]
        
        # Add to results
        results.append(result)
        
        # Update progress
        progress = ((index + 1) / total) * 100
        processing_status[task_id]["progress"] = progress
        processing_status[task_id]["results"] = results
        
        print(f"Completed: {result['facebook_url']} (Type: {result['type']}, Confidence: {result['confidence']})")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)
    
    # Update final status
    processing_status[task_id] = {
        "status": "completed",
        "progress": 100,
        "total": total,
        "results": results,
        "config": {
            "api_key": api_key,  # Store full key for requery
            "cse_id": cse_id,    # Store full ID for requery
            "openai_key": openai_key,
            "country_code": country_code,
            "language": language
        }
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
    <title>Facebook URL Search Tool - Google API</title>
    
    <!-- Favicon -->
    <link rel="icon" type="image/x-icon" href="/static/favicon.ico">
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32.png">
    <link rel="icon" type="image/png" sizes="512x512" href="/static/favicon-512.png">
    <link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png">
    
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
            max-width: 900px;
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
        
        .config-section {
            background: #f8f9ff;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            border: 2px solid #667eea;
        }
        
        .config-section h3 {
            color: #667eea;
            margin-bottom: 20px;
            font-size: 18px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            color: #333;
            font-weight: 600;
            margin-bottom: 8px;
        }
        
        .form-group select, .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        
        .form-group select:focus, .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
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
        
        .upload-section.drag-over {
            border-color: #38ef7d;
            background: #e8f5e9;
            transform: scale(1.02);
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
        
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            margin-left: 5px;
        }
        
        .badge-page { background: #38ef7d; color: white; }
        .badge-group { background: #ffd93d; color: #333; }
        .badge-other { background: #ff6b6b; color: white; }
        
        .autocomplete-wrapper {
            position: relative;
        }
        
        .autocomplete-input {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        
        .autocomplete-input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .api-credentials {
            background: #fff9e6;
            border: 2px solid #ffc107;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
        }
        
        .api-credentials h3 {
            color: #ff8f00;
            margin-bottom: 20px;
            font-size: 18px;
        }
        
        .password-toggle {
            position: relative;
        }
        
        .password-toggle-btn {
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            cursor: pointer;
            font-size: 18px;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Facebook URL Search Tool</h1>
        <p class="subtitle">Powered by Google Search API + AI Agent - Find Facebook business pages automatically</p>
        
        <div class="api-credentials">
            <h3>🔑 API Credentials</h3>
            <div class="form-row">
                <div class="form-group">
                    <label for="apiKey">Google API Key *</label>
                    <div class="password-toggle">
                        <input type="password" id="apiKey" class="autocomplete-input" placeholder="Enter your Google API Key">
                        <button type="button" class="password-toggle-btn" onclick="togglePasswordVisibility('apiKey')">👁️</button>
                    </div>
                </div>
                <div class="form-group">
                    <label for="cseId">Google CSE ID *</label>
                    <div class="password-toggle">
                        <input type="password" id="cseId" class="autocomplete-input" placeholder="Enter your Google CSE ID">
                        <button type="button" class="password-toggle-btn" onclick="togglePasswordVisibility('cseId')">👁️</button>
                    </div>
                </div>
            </div>
            <div class="form-group">
                <label for="openaiKey">OpenAI API Key *</label>
                <div class="password-toggle">
                    <input type="password" id="openaiKey" class="autocomplete-input" placeholder="Enter your OpenAI API Key">
                    <button type="button" class="password-toggle-btn" onclick="togglePasswordVisibility('openaiKey')">👁️</button>
                </div>
            </div>
        </div>
        
        <div class="instructions">
            <h3>📋 Instructions:</h3>
            <ul>
                <li>Enter your API credentials above (all required: Google API Key, CSE ID, OpenAI API Key)</li>
                <li>Configure Google search property (country) and language</li>
                <li>Upload a CSV or Excel file with two columns: <strong>business_name</strong> and <strong>location</strong></li>
                <li>Google Search API retrieves Facebook results, AI Agent intelligently filters and selects the best match</li>
                <li>The system finds official Facebook pages (or groups if not available) with AI-powered accuracy</li>
                <li>Download the results as a CSV with URL, Type, Confidence, and AI reasoning</li>
            </ul>
        </div>
        
        <div class="config-section">
            <h3>⚙️ Google Search Configuration</h3>
            <div class="form-row">
                <div class="form-group">
                    <label for="countryCode">Country Code *</label>
                    <input type="text" id="countryCode" class="autocomplete-input" list="countryList" 
                           placeholder="Type to search (e.g., United States, Italy, United Kingdom)">
                    <datalist id="countryList">
                        <option value="af">Afghanistan</option>
                        <option value="al">Albania</option>
                        <option value="dz">Algeria</option>
                        <option value="as">American Samoa</option>
                        <option value="ad">Andorra</option>
                        <option value="ao">Angola</option>
                        <option value="ai">Anguilla</option>
                        <option value="aq">Antarctica</option>
                        <option value="ag">Antigua and Barbuda</option>
                        <option value="ar">Argentina</option>
                        <option value="am">Armenia</option>
                        <option value="aw">Aruba</option>
                        <option value="au">Australia</option>
                        <option value="at">Austria</option>
                        <option value="az">Azerbaijan</option>
                        <option value="bs">Bahamas</option>
                        <option value="bh">Bahrain</option>
                        <option value="bd">Bangladesh</option>
                        <option value="bb">Barbados</option>
                        <option value="by">Belarus</option>
                        <option value="be">Belgium</option>
                        <option value="bz">Belize</option>
                        <option value="bj">Benin</option>
                        <option value="bm">Bermuda</option>
                        <option value="bt">Bhutan</option>
                        <option value="bo">Bolivia</option>
                        <option value="ba">Bosnia and Herzegovina</option>
                        <option value="bw">Botswana</option>
                        <option value="bv">Bouvet Island</option>
                        <option value="br">Brazil</option>
                        <option value="io">British Indian Ocean Territory</option>
                        <option value="bn">Brunei Darussalam</option>
                        <option value="bg">Bulgaria</option>
                        <option value="bf">Burkina Faso</option>
                        <option value="bi">Burundi</option>
                        <option value="kh">Cambodia</option>
                        <option value="cm">Cameroon</option>
                        <option value="ca">Canada</option>
                        <option value="cv">Cape Verde</option>
                        <option value="ky">Cayman Islands</option>
                        <option value="cf">Central African Republic</option>
                        <option value="td">Chad</option>
                        <option value="cl">Chile</option>
                        <option value="cn">China</option>
                        <option value="cx">Christmas Island</option>
                        <option value="cc">Cocos (Keeling) Islands</option>
                        <option value="co">Colombia</option>
                        <option value="km">Comoros</option>
                        <option value="cg">Congo</option>
                        <option value="cd">Congo, the Democratic Republic of the</option>
                        <option value="ck">Cook Islands</option>
                        <option value="cr">Costa Rica</option>
                        <option value="ci">Cote D'ivoire</option>
                        <option value="hr">Croatia</option>
                        <option value="cu">Cuba</option>
                        <option value="cy">Cyprus</option>
                        <option value="cz">Czech Republic</option>
                        <option value="dk">Denmark</option>
                        <option value="dj">Djibouti</option>
                        <option value="dm">Dominica</option>
                        <option value="do">Dominican Republic</option>
                        <option value="ec">Ecuador</option>
                        <option value="eg">Egypt</option>
                        <option value="sv">El Salvador</option>
                        <option value="gq">Equatorial Guinea</option>
                        <option value="er">Eritrea</option>
                        <option value="ee">Estonia</option>
                        <option value="et">Ethiopia</option>
                        <option value="fk">Falkland Islands (Malvinas)</option>
                        <option value="fo">Faroe Islands</option>
                        <option value="fj">Fiji</option>
                        <option value="fi">Finland</option>
                        <option value="fr">France</option>
                        <option value="gf">French Guiana</option>
                        <option value="pf">French Polynesia</option>
                        <option value="tf">French Southern Territories</option>
                        <option value="ga">Gabon</option>
                        <option value="gm">Gambia</option>
                        <option value="ge">Georgia</option>
                        <option value="de">Germany</option>
                        <option value="gh">Ghana</option>
                        <option value="gi">Gibraltar</option>
                        <option value="gr">Greece</option>
                        <option value="gl">Greenland</option>
                        <option value="gd">Grenada</option>
                        <option value="gp">Guadeloupe</option>
                        <option value="gu">Guam</option>
                        <option value="gt">Guatemala</option>
                        <option value="gn">Guinea</option>
                        <option value="gw">Guinea-Bissau</option>
                        <option value="gy">Guyana</option>
                        <option value="ht">Haiti</option>
                        <option value="hm">Heard Island and Mcdonald Islands</option>
                        <option value="va">Holy See (Vatican City State)</option>
                        <option value="hn">Honduras</option>
                        <option value="hk">Hong Kong</option>
                        <option value="hu">Hungary</option>
                        <option value="is">Iceland</option>
                        <option value="in">India</option>
                        <option value="id">Indonesia</option>
                        <option value="ir">Iran, Islamic Republic of</option>
                        <option value="iq">Iraq</option>
                        <option value="ie">Ireland</option>
                        <option value="il">Israel</option>
                        <option value="it">Italy</option>
                        <option value="jm">Jamaica</option>
                        <option value="jp">Japan</option>
                        <option value="jo">Jordan</option>
                        <option value="kz">Kazakhstan</option>
                        <option value="ke">Kenya</option>
                        <option value="ki">Kiribati</option>
                        <option value="kp">Korea, Democratic People's Republic of</option>
                        <option value="kr">Korea, Republic of</option>
                        <option value="kw">Kuwait</option>
                        <option value="kg">Kyrgyzstan</option>
                        <option value="la">Lao People's Democratic Republic</option>
                        <option value="lv">Latvia</option>
                        <option value="lb">Lebanon</option>
                        <option value="ls">Lesotho</option>
                        <option value="lr">Liberia</option>
                        <option value="ly">Libyan Arab Jamahiriya</option>
                        <option value="li">Liechtenstein</option>
                        <option value="lt">Lithuania</option>
                        <option value="lu">Luxembourg</option>
                        <option value="mo">Macao</option>
                        <option value="mk">Macedonia, the Former Yugosalv Republic of</option>
                        <option value="mg">Madagascar</option>
                        <option value="mw">Malawi</option>
                        <option value="my">Malaysia</option>
                        <option value="mv">Maldives</option>
                        <option value="ml">Mali</option>
                        <option value="mt">Malta</option>
                        <option value="mh">Marshall Islands</option>
                        <option value="mq">Martinique</option>
                        <option value="mr">Mauritania</option>
                        <option value="mu">Mauritius</option>
                        <option value="yt">Mayotte</option>
                        <option value="mx">Mexico</option>
                        <option value="fm">Micronesia, Federated States of</option>
                        <option value="md">Moldova, Republic of</option>
                        <option value="mc">Monaco</option>
                        <option value="mn">Mongolia</option>
                        <option value="ms">Montserrat</option>
                        <option value="ma">Morocco</option>
                        <option value="mz">Mozambique</option>
                        <option value="mm">Myanmar</option>
                        <option value="na">Namibia</option>
                        <option value="nr">Nauru</option>
                        <option value="np">Nepal</option>
                        <option value="nl">Netherlands</option>
                        <option value="an">Netherlands Antilles</option>
                        <option value="nc">New Caledonia</option>
                        <option value="nz">New Zealand</option>
                        <option value="ni">Nicaragua</option>
                        <option value="ne">Niger</option>
                        <option value="ng">Nigeria</option>
                        <option value="nu">Niue</option>
                        <option value="nf">Norfolk Island</option>
                        <option value="mp">Northern Mariana Islands</option>
                        <option value="no">Norway</option>
                        <option value="om">Oman</option>
                        <option value="pk">Pakistan</option>
                        <option value="pw">Palau</option>
                        <option value="ps">Palestinian Territory, Occupied</option>
                        <option value="pa">Panama</option>
                        <option value="pg">Papua New Guinea</option>
                        <option value="py">Paraguay</option>
                        <option value="pe">Peru</option>
                        <option value="ph">Philippines</option>
                        <option value="pn">Pitcairn</option>
                        <option value="pl">Poland</option>
                        <option value="pt">Portugal</option>
                        <option value="pr">Puerto Rico</option>
                        <option value="qa">Qatar</option>
                        <option value="re">Reunion</option>
                        <option value="ro">Romania</option>
                        <option value="ru">Russian Federation</option>
                        <option value="rw">Rwanda</option>
                        <option value="sh">Saint Helena</option>
                        <option value="kn">Saint Kitts and Nevis</option>
                        <option value="lc">Saint Lucia</option>
                        <option value="pm">Saint Pierre and Miquelon</option>
                        <option value="vc">Saint Vincent and the Grenadines</option>
                        <option value="ws">Samoa</option>
                        <option value="sm">San Marino</option>
                        <option value="st">Sao Tome and Principe</option>
                        <option value="sa">Saudi Arabia</option>
                        <option value="sn">Senegal</option>
                        <option value="cs">Serbia and Montenegro</option>
                        <option value="sc">Seychelles</option>
                        <option value="sl">Sierra Leone</option>
                        <option value="sg">Singapore</option>
                        <option value="sk">Slovakia</option>
                        <option value="si">Slovenia</option>
                        <option value="sb">Solomon Islands</option>
                        <option value="so">Somalia</option>
                        <option value="za">South Africa</option>
                        <option value="gs">South Georgia and the South Sandwich Islands</option>
                        <option value="es">Spain</option>
                        <option value="lk">Sri Lanka</option>
                        <option value="sd">Sudan</option>
                        <option value="sr">Suriname</option>
                        <option value="sj">Svalbard and Jan Mayen</option>
                        <option value="sz">Swaziland</option>
                        <option value="se">Sweden</option>
                        <option value="ch">Switzerland</option>
                        <option value="sy">Syrian Arab Republic</option>
                        <option value="tw">Taiwan, Province of China</option>
                        <option value="tj">Tajikistan</option>
                        <option value="tz">Tanzania, United Republic of</option>
                        <option value="th">Thailand</option>
                        <option value="tl">Timor-Leste</option>
                        <option value="tg">Togo</option>
                        <option value="tk">Tokelau</option>
                        <option value="to">Tonga</option>
                        <option value="tt">Trinidad and Tobago</option>
                        <option value="tn">Tunisia</option>
                        <option value="tr">Turkey</option>
                        <option value="tm">Turkmenistan</option>
                        <option value="tc">Turks and Caicos Islands</option>
                        <option value="tv">Tuvalu</option>
                        <option value="ug">Uganda</option>
                        <option value="ua">Ukraine</option>
                        <option value="ae">United Arab Emirates</option>
                        <option value="uk">United Kingdom</option>
                        <option value="us">United States</option>
                        <option value="um">United States Minor Outlying Islands</option>
                        <option value="uy">Uruguay</option>
                        <option value="uz">Uzbekistan</option>
                        <option value="vu">Vanuatu</option>
                        <option value="ve">Venezuela</option>
                        <option value="vn">Viet Nam</option>
                        <option value="vg">Virgin Islands, British</option>
                        <option value="vi">Virgin Islands, U.S.</option>
                        <option value="wf">Wallis and Futuna</option>
                        <option value="eh">Western Sahara</option>
                        <option value="ye">Yemen</option>
                        <option value="zm">Zambia</option>
                        <option value="zw">Zimbabwe</option>
                    </datalist>
                </div>
                <div class="form-group">
                    <label for="language">Interface Language *</label>
                    <input type="text" id="language" class="autocomplete-input" list="languageList" 
                           placeholder="Type to search (e.g., English, Italian, French)">
                    <datalist id="languageList">
                        <option value="af">Afrikaans</option>
                        <option value="sq">Albanian</option>
                        <option value="sm">Amharic</option>
                        <option value="ar">Arabic</option>
                        <option value="az">Azerbaijani</option>
                        <option value="eu">Basque</option>
                        <option value="be">Belarusian</option>
                        <option value="bn">Bengali</option>
                        <option value="bh">Bihari</option>
                        <option value="bs">Bosnian</option>
                        <option value="bg">Bulgarian</option>
                        <option value="ca">Catalan</option>
                        <option value="zh-CN">Chinese (Simplified)</option>
                        <option value="zh-TW">Chinese (Traditional)</option>
                        <option value="hr">Croatian</option>
                        <option value="cs">Czech</option>
                        <option value="da">Danish</option>
                        <option value="nl">Dutch</option>
                        <option value="en">English</option>
                        <option value="eo">Esperanto</option>
                        <option value="et">Estonian</option>
                        <option value="fo">Faroese</option>
                        <option value="fi">Finnish</option>
                        <option value="fr">French</option>
                        <option value="fy">Frisian</option>
                        <option value="gl">Galician</option>
                        <option value="ka">Georgian</option>
                        <option value="de">German</option>
                        <option value="el">Greek</option>
                        <option value="gu">Gujarati</option>
                        <option value="iw">Hebrew</option>
                        <option value="hi">Hindi</option>
                        <option value="hu">Hungarian</option>
                        <option value="is">Icelandic</option>
                        <option value="id">Indonesian</option>
                        <option value="ia">Interlingua</option>
                        <option value="ga">Irish</option>
                        <option value="it">Italian</option>
                        <option value="ja">Japanese</option>
                        <option value="jw">Javanese</option>
                        <option value="kn">Kannada</option>
                        <option value="ko">Korean</option>
                        <option value="la">Latin</option>
                        <option value="lv">Latvian</option>
                        <option value="lt">Lithuanian</option>
                        <option value="mk">Macedonian</option>
                        <option value="ms">Malay</option>
                        <option value="ml">Malayam</option>
                        <option value="mt">Maltese</option>
                        <option value="mr">Marathi</option>
                        <option value="ne">Nepali</option>
                        <option value="no">Norwegian</option>
                        <option value="nn">Norwegian (Nynorsk)</option>
                        <option value="oc">Occitan</option>
                        <option value="fa">Persian</option>
                        <option value="pl">Polish</option>
                        <option value="pt-BR">Portuguese (Brazil)</option>
                        <option value="pt-PT">Portuguese (Portugal)</option>
                        <option value="pa">Punjabi</option>
                        <option value="ro">Romanian</option>
                        <option value="ru">Russian</option>
                        <option value="gd">Scots Gaelic</option>
                        <option value="sr">Serbian</option>
                        <option value="si">Sinhalese</option>
                        <option value="sk">Slovak</option>
                        <option value="sl">Slovenian</option>
                        <option value="es">Spanish</option>
                        <option value="su">Sudanese</option>
                        <option value="sw">Swahili</option>
                        <option value="sv">Swedish</option>
                        <option value="tl">Tagalog</option>
                        <option value="ta">Tamil</option>
                        <option value="te">Telugu</option>
                        <option value="th">Thai</option>
                        <option value="ti">Tigrinya</option>
                        <option value="tr">Turkish</option>
                        <option value="uk">Ukrainian</option>
                        <option value="ur">Urdu</option>
                        <option value="uz">Uzbek</option>
                        <option value="vi">Vietnamese</option>
                        <option value="cy">Welsh</option>
                        <option value="xh">Xhosa</option>
                        <option value="zu">Zulu</option>
                    </datalist>
                </div>
            </div>
        </div>
        
        <div class="upload-section" id="uploadSection">
            <input type="file" id="fileInput" accept=".csv,.xlsx,.xls">
            <label for="fileInput" class="upload-label">📁 Choose File</label>
            <div class="file-info" id="fileInfo">Drag & drop file here or click to browse</div>
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
            <div id="notFoundInfo" style="display: none; margin: 15px 0; padding: 15px; background: #fff3cd; border-radius: 10px; border-left: 4px solid #ffc107;">
                <strong>⚠️ Not Found:</strong> <span id="notFoundCount">0</span> records were not found.
                <button class="btn btn-primary" onclick="requeryNotFound()" style="margin-left: 15px; padding: 10px 20px;">
                    🔄 Requery Not Found Records
                </button>
            </div>
            <button class="btn btn-success" onclick="downloadResults()">
                📥 Download Results CSV
            </button>
            <div id="resultsPreview"></div>
        </div>
    </div>
    
    <script>
        let selectedFile = null;
        let currentTaskId = null;
        let selectedCountryCode = 'us';
        let selectedLanguageCode = 'en';
        
        // Build country code to name mapping
        const countryMap = {};
        const countryOptions = document.querySelectorAll('#countryList option');
        countryOptions.forEach(option => {
            countryMap[option.value] = option.textContent;
        });
        
        // Build language code to name mapping
        const languageMap = {};
        const languageOptions = document.querySelectorAll('#languageList option');
        languageOptions.forEach(option => {
            languageMap[option.value] = option.textContent;
        });
        
        // Handle country code selection (only when user selects from datalist)
        document.getElementById('countryCode').addEventListener('change', function(e) {
            const value = e.target.value.toLowerCase().trim();
            // Check if it's a valid code
            if (countryMap[value]) {
                selectedCountryCode = value;
                e.target.value = countryMap[value]; // Update display to full name
            } else {
                // Check if user entered the full name, find the code
                for (const [code, name] of Object.entries(countryMap)) {
                    if (name.toLowerCase() === e.target.value.toLowerCase().trim()) {
                        selectedCountryCode = code;
                        e.target.value = name; // Ensure proper capitalization
                        break;
                    }
                }
            }
        });
        
        // Handle country code blur - ensure display shows full name
        document.getElementById('countryCode').addEventListener('blur', function(e) {
            const value = e.target.value.toLowerCase().trim();
            // Check if it's a valid code
            if (countryMap[value]) {
                selectedCountryCode = value;
                e.target.value = countryMap[value];
            } else {
                // Check if user entered the full name, find the code
                for (const [code, name] of Object.entries(countryMap)) {
                    if (name.toLowerCase() === value) {
                        selectedCountryCode = code;
                        e.target.value = name;
                        break;
                    }
                }
            }
        });
        
        // Handle language selection (only when user selects from datalist)
        document.getElementById('language').addEventListener('change', function(e) {
            const value = e.target.value.toLowerCase().trim();
            // Check if it's a valid code
            if (languageMap[value]) {
                selectedLanguageCode = value;
                e.target.value = languageMap[value]; // Update display to full name
            } else {
                // Check if user entered the full name, find the code
                for (const [code, name] of Object.entries(languageMap)) {
                    if (name.toLowerCase() === e.target.value.toLowerCase().trim()) {
                        selectedLanguageCode = code;
                        e.target.value = name; // Ensure proper capitalization
                        break;
                    }
                }
            }
        });
        
        // Handle language blur - ensure display shows full name
        document.getElementById('language').addEventListener('blur', function(e) {
            const value = e.target.value.toLowerCase().trim();
            // Check if it's a valid code
            if (languageMap[value]) {
                selectedLanguageCode = value;
                e.target.value = languageMap[value];
            } else {
                // Check if user entered the full name, find the code
                for (const [code, name] of Object.entries(languageMap)) {
                    if (name.toLowerCase() === value) {
                        selectedLanguageCode = code;
                        e.target.value = name;
                        break;
                    }
                }
            }
        });
        
        // Initialize display with full names
        document.getElementById('countryCode').value = countryMap['us'] || 'United States';
        document.getElementById('language').value = languageMap['en'] || 'English';
        
        // Password toggle functionality
        function togglePasswordVisibility(inputId) {
            const input = document.getElementById(inputId);
            if (input.type === 'password') {
                input.type = 'text';
            } else {
                input.type = 'password';
            }
        }
        
        // File input change handler
        document.getElementById('fileInput').addEventListener('change', function(e) {
            selectedFile = e.target.files[0];
            if (selectedFile) {
                document.getElementById('fileInfo').textContent = `Selected: ${selectedFile.name}`;
                updateProcessButtonState();
            }
        });
        
        // Check if all required fields are filled
        function updateProcessButtonState() {
            const apiKey = document.getElementById('apiKey').value.trim();
            const cseId = document.getElementById('cseId').value.trim();
            const openaiKey = document.getElementById('openaiKey').value.trim();
            const hasFile = selectedFile !== null;
            
            document.getElementById('processBtn').disabled = !(apiKey && cseId && openaiKey && hasFile);
        }
        
        // Add listeners to API credential inputs
        document.getElementById('apiKey').addEventListener('input', updateProcessButtonState);
        document.getElementById('cseId').addEventListener('input', updateProcessButtonState);
        document.getElementById('openaiKey').addEventListener('input', updateProcessButtonState);
        
        // Drag and drop handlers
        const uploadSection = document.getElementById('uploadSection');
        
        uploadSection.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            uploadSection.classList.add('drag-over');
        });
        
        uploadSection.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            uploadSection.classList.remove('drag-over');
        });
        
        uploadSection.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            uploadSection.classList.remove('drag-over');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                const file = files[0];
                
                // Check file extension
                const fileName = file.name.toLowerCase();
                if (fileName.endsWith('.csv') || fileName.endsWith('.xlsx') || fileName.endsWith('.xls')) {
                    selectedFile = file;
                    document.getElementById('fileInfo').textContent = `Selected: ${file.name}`;
                    updateProcessButtonState();
                } else {
                    alert('Please upload a CSV or Excel file (.csv, .xlsx, .xls)');
                }
            }
        });
        
        async function processFile() {
            if (!selectedFile) return;
            
            // Validate API credentials
            const apiKey = document.getElementById('apiKey').value.trim();
            const cseId = document.getElementById('cseId').value.trim();
            const openaiKey = document.getElementById('openaiKey').value.trim();
            
            if (!apiKey || !cseId || !openaiKey) {
                alert('Please enter all required API credentials: Google API Key, CSE ID, and OpenAI API Key');
                return;
            }
            
            if (!selectedCountryCode || !selectedLanguageCode) {
                alert('Please select country code and language');
                return;
            }
            
            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('api_key', apiKey);
            formData.append('cse_id', cseId);
            formData.append('openai_key', openaiKey);
            formData.append('country_code', selectedCountryCode);  // Use the code, not the display name
            formData.append('language', selectedLanguageCode);     // Use the code, not the display name
            
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
            
            const config = data.config || {};
            const countryName = countryMap[config.country_code] || config.country_code || 'United States';
            const languageName = languageMap[config.language] || config.language || 'English';
            document.getElementById('resultsSummary').textContent = 
                `Processed ${data.total} records successfully using country: ${countryName}, language: ${languageName}`;
            
            // Check for not found results
            checkNotFoundResults();
            
            // Show preview of first few results
            const preview = document.getElementById('resultsPreview');
            preview.innerHTML = '<h4 style="margin-top: 20px;">Preview (first 5 results):</h4>';
            
            data.results.slice(0, 5).forEach(result => {
                const confidenceClass = result.confidence >= 0.6 ? 'confidence-high' : 
                                       result.confidence >= 0.3 ? 'confidence-medium' : 'confidence-low';
                
                let typeBadge = '';
                if (result.type === 'page') {
                    typeBadge = '<span class="badge badge-page">PAGE</span>';
                } else if (result.type === 'group') {
                    typeBadge = '<span class="badge badge-group">GROUP</span>';
                } else {
                    typeBadge = '<span class="badge badge-other">OTHER</span>';
                }
                
                preview.innerHTML += `
                    <div class="result-item ${confidenceClass}">
                        <strong>${result.business_name}</strong> - ${result.location} ${typeBadge}<br>
                        <small>URL: <a href="${result.facebook_url}" target="_blank">${result.facebook_url}</a></small><br>
                        <small>Confidence: ${result.confidence} | ${result.notes}</small>
                    </div>
                `;
            });
        }
        
        async function checkNotFoundResults() {
            try {
                const response = await fetch(`/not_found/${currentTaskId}`);
                const data = await response.json();
                
                if (data.not_found_count > 0) {
                    document.getElementById('notFoundInfo').style.display = 'block';
                    document.getElementById('notFoundCount').textContent = data.not_found_count;
                }
            } catch (error) {
                console.error('Error checking not found results:', error);
            }
        }
        
        async function requeryNotFound() {
            if (!currentTaskId) return;
            
            if (!confirm('This will requery all records that were not found. Continue?')) {
                return;
            }
            
            try {
                const response = await fetch(`/requery/${currentTaskId}`, {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                if (data.requery_task_id) {
                    alert(`Requerying ${data.not_found_count} records. Task ID: ${data.requery_task_id}`);
                    
                    // Switch to the new requery task
                    currentTaskId = data.requery_task_id;
                    
                    // Show progress section and hide results
                    document.getElementById('resultsSection').style.display = 'none';
                    document.getElementById('progressSection').style.display = 'block';
                    
                    // Start polling for the new task
                    pollProgress();
                } else {
                    alert(data.message);
                }
                
            } catch (error) {
                alert('Error starting requery: ' + error.message);
            }
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
async def upload_file(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    api_key: str = Form(...),
    cse_id: str = Form(...),
    openai_key: str = Form(...),
    country_code: str = Form("us"),
    language: str = Form("en")
):
    """
    Upload CSV/Excel file and start processing with user-provided API credentials
    """
    try:
        # Validate API credentials
        if not api_key or not cse_id or not openai_key:
            raise HTTPException(status_code=400, detail="Google API Key, CSE ID, and OpenAI API Key are all required")
        
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
                detail=f"File must contain columns: business_name, location. Found: {list(df.columns)}"
            )
        
        # Convert to list of dicts
        records = df[required_cols].to_dict('records')
        
        # Generate task ID
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Start background processing with user credentials
        background_tasks.add_task(
            process_batch_with_config, 
            records, 
            task_id,
            api_key,
            cse_id,
            openai_key,
            country_code,
            language
        )
        
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


@app.get("/not_found/{task_id}")
async def get_not_found_results(task_id: str):
    """
    Get records that were not found for a specific task
    """
    if task_id not in processing_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = processing_status[task_id]
    
    if status["status"] != "completed":
        raise HTTPException(status_code=400, detail="Processing not completed yet")
    
    # Filter for not found results
    not_found = []
    for result in status["results"]:
        if result["facebook_url"] in ["Not found", "Error"] or result["type"] in ["not_found", "error"]:
            not_found.append({
                "business_name": result["business_name"],
                "location": result["location"]
            })
    
    return {
        "task_id": task_id,
        "not_found_count": len(not_found),
        "total_count": len(status["results"]),
        "not_found_records": not_found
    }


@app.post("/requery/{task_id}")
async def requery_not_found(
    task_id: str,
    background_tasks: BackgroundTasks
):
    """
    Requery records that were not found in a previous task
    Uses the same API credentials as the original task
    """
    if task_id not in processing_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = processing_status[task_id]
    
    if status["status"] != "completed":
        raise HTTPException(status_code=400, detail="Original task not completed yet")
    
    # Get config from original task (including credentials)
    config = status.get("config", {})
    api_key = config.get("api_key")
    cse_id = config.get("cse_id")
    openai_key = config.get("openai_key")
    country_code = config.get("country_code", "us")
    language = config.get("language", "en")
    
    if not api_key or not cse_id:
        raise HTTPException(status_code=400, detail="Original task credentials not found")
    
    # Filter for not found results
    not_found_records = []
    for result in status["results"]:
        if result["facebook_url"] in ["Not found", "Error"] or result["type"] in ["not_found", "error"]:
            not_found_records.append({
                "business_name": result["business_name"],
                "location": result["location"]
            })
    
    if not not_found_records:
        return {
            "message": "No records to requery - all were found!",
            "not_found_count": 0
        }
    
    # Generate new task ID for requery
    requery_task_id = f"requery_{task_id}_{datetime.now().strftime('%H%M%S')}"
    
    # Start background processing for not found records with same credentials
    background_tasks.add_task(
        process_batch_with_config,
        not_found_records,
        requery_task_id,
        api_key,
        cse_id,
        openai_key,
        country_code,
        language
    )
    
    return {
        "message": f"Requerying {len(not_found_records)} not found records",
        "original_task_id": task_id,
        "requery_task_id": requery_task_id,
        "not_found_count": len(not_found_records)
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "google_api_configured": bool(GOOGLE_API_KEY and GOOGLE_CSE_ID),
        "openai_api_configured": bool(OPENAI_API_KEY),
        "ai_filtering_enabled": bool(openai_client)
    }


if __name__ == "__main__":
    print("Starting Facebook URL Search Tool (Google API)...")
    print("Server will be available at: http://localhost:8000")
    print("Make sure GOOGLE_API_KEY and GOOGLE_CSE_ID are set in environment variables")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
