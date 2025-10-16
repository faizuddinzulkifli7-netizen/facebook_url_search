# Facebook URL Search Automation Tool

🔍 **Web-based automation tool powered by Google Search API + AI Agent** that automatically finds official Facebook business pages (or groups) for a list of businesses.

## 📋 Features

- ✅ Upload CSV or Excel files with business names and locations
- ✅ **Hybrid approach**: Google Search API + AI-powered filtering
- ✅ **AI Agent** (GPT-4o-mini) intelligently analyzes and selects best Facebook URL
- ✅ Customizable Google property (google.com, google.it, google.co.uk, etc.) and language
- ✅ Smart URL filtering (excludes /about, /posts, /photos, /media, etc.)
- ✅ Context-aware decision making with detailed AI reasoning
- ✅ Advanced URL categorization (page/group/other)
- ✅ Intelligent name matching with variations and abbreviations
- ✅ Confidence scoring with transparent reasoning
- ✅ Automatic fallback to rule-based filtering if AI unavailable
- ✅ Batch processing with progress tracking
- ✅ Real-time progress monitoring
- ✅ Download structured CSV results with AI reasoning
- ✅ Beautiful, modern web interface

## 🎯 Output Format

The tool generates a CSV file with the following columns:

| Column | Description |
|--------|-------------|
| **Business Name** | Original business name from input |
| **Location** | Location text provided |
| **Facebook URL** | Best-matching Facebook Page or Group URL |
| **Type** | Indicates whether result is a "page" or "group" |
| **Confidence** | Score between 0.0-1.0 indicating match quality |
| **Notes** | Explanation (e.g., "Verified page mentioning Coral Gables") |

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- **Google API key** (get one at https://console.cloud.google.com/apis/credentials)
- **Google Custom Search Engine ID** (create one at https://programmablesearchengine.google.com/)
- **OpenAI API key** (get one at https://platform.openai.com/api-keys) - for AI-powered filtering

### Installation

1. **Clone or download this repository**

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up your API credentials**

Create a `.env` file in the project root with your credentials:
```
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_CSE_ID=your_custom_search_engine_id_here
OPENAI_API_KEY=sk-your-openai-api-key-here
```

#### How to get Google API credentials:

**Step 1: Get Google API Key**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the "Custom Search API"
4. Go to "Credentials" and create an API key

**Step 2: Create Custom Search Engine**
1. Go to [Programmable Search Engine](https://programmablesearchengine.google.com/)
2. Click "Add" to create a new search engine
3. For "Sites to search", enter: `www.facebook.com/*`
4. Give it a name (e.g., "Facebook Search")
5. Click "Create"
6. Copy the "Search engine ID" (this is your GOOGLE_CSE_ID)

**Step 3: Get OpenAI API Key** (for AI filtering)
1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Go to API Keys section
4. Click "Create new secret key"
5. Copy the key (starts with `sk-proj-` or `sk-`)
6. This is your OPENAI_API_KEY

Alternatively, set as environment variables:
```bash
# Windows (PowerShell)
$env:GOOGLE_API_KEY="your_api_key_here"
$env:GOOGLE_CSE_ID="your_cse_id_here"
$env:OPENAI_API_KEY="sk-your-openai-key-here"

# Windows (CMD)
set GOOGLE_API_KEY=your_api_key_here
set GOOGLE_CSE_ID=your_cse_id_here
set OPENAI_API_KEY=sk-your-openai-key-here

# Linux/Mac
export GOOGLE_API_KEY=your_api_key_here
export GOOGLE_CSE_ID=your_cse_id_here
export OPENAI_API_KEY=sk-your-openai-key-here
```

4. **Run the application**
```bash
python main.py
```

5. **Open your browser**
```
http://localhost:8000
```

## 📖 Usage

### Input File Format

Your input file (CSV or Excel) should have **two columns**:

| Business Name | Location |
|--------------|----------|
| Riviera Country Club | Coral Gables FL |
| Starbucks Coffee | Miami FL |
| Tesla Service Center | Fort Lauderdale FL |

**Column names are case-insensitive** and spaces are handled automatically.

### Using the Web Interface

1. **Configure search settings** - Select Google property (domain) and language
2. **Upload your file** - Click "Choose File" and select your CSV or Excel file
3. **Start processing** - Click "Start Processing" button
4. **Monitor progress** - Watch the real-time progress bar
5. **Download results** - Once complete, click "Download Results CSV"

### Google Search Configuration

The tool allows you to customize:
- **Google Property**: Choose which Google domain to use (google.com, google.it, google.co.uk, etc.)
- **Language**: Select the search language (en, it, fr, es, de, etc.)

This is useful for finding localized Facebook pages based on your target region.

### Sample File

A sample input file (`sample_input.csv`) is included in the repository for testing.

## ⚙️ Configuration

### Search Results Limit

The tool retrieves up to **20 results per search** from Google (Note: Google API allows max 10 per request).

To adjust, edit `main.py` around line 338:

```python
result = google_service.cse().list(
    q=search_query,
    cx=GOOGLE_CSE_ID,
    num=min(num_results, 10),  # Change this value (max 10)
    ...
).execute()
```

### URL Quality Scoring

The tool uses intelligent URL filtering to avoid "bad" URLs:
- Excludes URLs with `/about`, `/posts`, `/photos`, `/media`, `/videos`, etc.
- Penalizes personal profiles (`profile.php`)
- Slightly penalizes groups (acceptable but not ideal)
- Prioritizes clean business page URLs

You can customize the bad patterns in `main.py` around line 78:

```python
BAD_URL_PATTERNS = [
    r'/about/?$',
    r'/posts/?',
    # Add or remove patterns here
]
```

### Rate Limiting

Default: **0.5 second delay** between requests to avoid API rate limits.

To adjust, edit `main.py` around line 454:

```python
# Small delay to avoid rate limiting
await asyncio.sleep(0.5)  # Change delay in seconds
```

### Server Port

To change the default port (8000), edit the last line in `main.py`:

```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # Change port number
```

Or set environment variable:
```bash
PORT=3000 python main.py
```

## 🧪 Testing

### Test with Sample Data

1. Use the included `sample_input.csv` file
2. Upload it through the web interface
3. The tool will process 10 businesses and show results

### API Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "google_api_configured": true
}
```

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web interface |
| `/upload` | POST | Upload file and start processing |
| `/status/{task_id}` | GET | Get processing status |
| `/download/{task_id}` | GET | Download results CSV |
| `/health` | GET | Health check |

## 🛠️ Technology Stack

- **Backend**: FastAPI (Python)
- **Search API**: Google Custom Search JSON API
- **AI Engine**: OpenAI GPT-4o-mini (for intelligent filtering)
- **Data Processing**: Pandas
- **File Handling**: openpyxl, xlrd
- **Async Processing**: asyncio
- **Frontend**: HTML/CSS/JavaScript (vanilla)

### Hybrid Architecture: Google Search + AI Agent

This tool uses a **2-stage approach** for maximum accuracy:

#### Stage 1: Google Search API
- ✅ Direct Google search with `site:facebook.com` restriction
- ✅ Customizable Google property and language
- ✅ Retrieves up to 10 real-time Facebook results
- ✅ Returns URLs with titles and descriptions

#### Stage 2: AI-Powered Filtering
- ✅ **AI Agent** analyzes all search results
- ✅ Context-aware decision making
- ✅ Understands business name variations
- ✅ Applies intelligent filtering rules
- ✅ Selects best matching URL
- ✅ Provides detailed reasoning
- ✅ Automatic fallback to rule-based if AI unavailable

### URL Categorization Logic

The tool categorizes Facebook URLs into three types:

1. **page** - Business pages:
   - `facebook.com/BusinessName/` (username pattern)
   - `facebook.com/p/Business-Name-12345/` (modern /p/ pattern)

2. **group** - Facebook groups:
   - `facebook.com/groups/GroupName/`

3. **other** - Personal profiles or unclear:
   - `facebook.com/profile.php?id=12345`
   - Any URL that doesn't match page or group patterns

### Confidence Scoring

Confidence scores (0.0 to 1.0) are calculated based on:
- **URL Quality Score (40%)**: Clean URL structure, no bad paths
- **Name Match Score (60%)**: How well business name matches URL and metadata

**Score interpretation:**
- **0.8-1.0**: Excellent match (high confidence)
- **0.6-0.8**: Good match
- **0.4-0.6**: Moderate match
- **0.0-0.4**: Low confidence (manual review recommended)

## 💰 Cost Estimation

### Google Custom Search JSON API
- **Free tier**: 100 queries per day
- **Paid**: $5 per 1,000 queries (after free tier)
- **Cost per business**: ~$0.005

### OpenAI API (GPT-4o-mini for AI filtering)
- **Input**: ~500 tokens per request (~$0.000075)
- **Output**: ~100 tokens per request (~$0.000060)
- **Cost per business**: ~$0.000135 (negligible!)

### Total Cost per Business
- Google API: $0.005
- OpenAI AI filtering: $0.000135
- **Total**: ~**$0.0051 per business**

### Batch Estimates
| Businesses | Google API | OpenAI API | **Total** |
|------------|-----------|-----------|---------|
| **100** | FREE | ~$0.01 | **~$0.01** (free tier) |
| **1,000** | ~$5 | ~$0.14 | **~$5.14** |
| **10,000** | ~$50 | ~$1.40 | **~$51.40** |

**AI filtering adds less than 3% to total cost** while dramatically improving accuracy!

## ⚠️ Important Notes

1. **API Key Security**: Never commit your `.env` file or share your API credentials
2. **Required API Keys**: 
   - **Google API Key** + **CSE ID** (for search results)
   - **OpenAI API Key** (for AI-powered filtering)
   - Tool falls back to rule-based filtering if OpenAI key is missing
3. **Rate Limits**: 
   - Google API free tier: 100 queries/day
   - OpenAI API: Based on your tier (usually sufficient)
   - Paid tier: Higher limits based on billing
4. **Search Accuracy**: 
   - Google provides real-time search results
   - AI agent provides intelligent filtering with reasoning
   - Results include detailed AI explanation in Notes column
5. **Manual Review**: Always review low-confidence results (< 0.6) manually
6. **Facebook Changes**: Facebook URL structures may change over time
7. **Custom Search Engine Setup**: Make sure your CSE is configured to search `www.facebook.com/*` only
8. **AI Reasoning**: Check the "Notes" column to understand why each URL was selected

## 🐛 Troubleshooting

### "GOOGLE_API_KEY not set" or "GOOGLE_CSE_ID not set" warning

- Make sure you created a `.env` file with both credentials
- Or set the environment variables before running the script
- Verify your API key is valid and Custom Search API is enabled in Google Cloud Console

### "Google API error: ..." errors

- **Quota exceeded**: You've hit the free tier limit (100/day) or paid quota
  - Wait for quota reset or upgrade to paid tier
- **API not enabled**: Enable Custom Search API in Google Cloud Console
- **Invalid CSE ID**: Verify your Custom Search Engine ID is correct
- **Invalid API key**: Check your API key in Google Cloud Console

### "Rate limit exceeded" error

- Increase the delay between requests in `main.py` (around line 454)
- Default is 0.5 seconds, try increasing to 1-2 seconds

### File upload fails

- Ensure file has "Business Name" and "Location" columns
- Check file format (CSV or Excel only)
- File size limit: reasonable for typical batch processing

### Low confidence scores

- Business name or location may be incorrect
- Facebook page might not exist
- Manual verification recommended

## 🔄 Deployment Options

### Local Development
```bash
python main.py
```

### Production Deployment

**Option 1: Docker** (create Dockerfile)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

**Option 2: Cloud Platforms**
- **Heroku**: Use `Procfile` with `web: python main.py`
- **Railway**: Auto-detects Python and runs main.py
- **Render**: Configure web service with build command `pip install -r requirements.txt`
- **AWS/Azure/GCP**: Use their Python web app services

## 📝 License

This project is provided as-is for automation purposes.

## 🤝 Support

For issues or questions:
1. Check this README thoroughly
2. Review the troubleshooting section
3. Check OpenAI API documentation
4. Verify your API key and account status

## 🎯 Roadmap / Future Enhancements

- [ ] Add support for batch retry of failed searches
- [ ] Export to Excel with formatting
- [ ] Add filters for confidence threshold
- [ ] Dashboard with analytics
- [ ] Multi-language support
- [ ] Integration with Google Sheets
- [ ] Scheduled batch processing
- [ ] Email notifications on completion

---

**Made with ❤️ using Google Custom Search JSON API and FastAPI**

