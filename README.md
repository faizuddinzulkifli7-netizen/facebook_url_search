# Facebook URL Search Automation Tool

🔍 **Web-based automation tool powered by OpenAI API** that automatically finds official Facebook business pages (or groups) for a list of businesses.

## 📋 Features

- ✅ Upload CSV or Excel files with business names and locations
- ✅ Automatic Facebook page/group search using OpenAI API
- ✅ Smart preference for official business Pages over Groups
- ✅ Confidence scoring for match quality
- ✅ Batch processing with rate limiting
- ✅ Real-time progress tracking
- ✅ Download structured CSV results
- ✅ Beautiful, user-friendly web interface

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
- OpenAI API key (get one at https://platform.openai.com/api-keys)

### Installation

1. **Clone or download this repository**

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up your OpenAI API key**

Create a `.env` file in the project root:
```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:
```
OPENAI_API_KEY=sk-your-actual-api-key-here
```

Alternatively, set it as an environment variable:
```bash
# Windows (PowerShell)
$env:OPENAI_API_KEY="sk-your-actual-api-key-here"

# Windows (CMD)
set OPENAI_API_KEY=sk-your-actual-api-key-here

# Linux/Mac
export OPENAI_API_KEY=sk-your-actual-api-key-here
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

1. **Upload your file** - Click "Choose File" and select your CSV or Excel file
2. **Start processing** - Click "Start Processing" button
3. **Monitor progress** - Watch the real-time progress bar
4. **Download results** - Once complete, click "Download Results CSV"

### Sample File

A sample input file (`sample_input.csv`) is included in the repository for testing.

## ⚙️ Configuration

### API Model Selection

The tool uses `gpt-4o` by default for **best web search integration**. This model has built-in web search capabilities that provide more accurate, real-time results.

To use a different model, edit `main.py`:

```python
# Line ~95 in main.py
response = await asyncio.to_thread(
    openai.chat.completions.create,
    model="gpt-4o",  # Options: "gpt-4o-mini", "gpt-4-turbo", "gpt-4o"
    ...
)
```

**Model recommendations:**
- **gpt-4o** (default): Best web search, most accurate results
- **gpt-4o-mini**: More cost-effective, slightly less accurate
- **gpt-4-turbo**: Good balance of cost and performance

### Rate Limiting

Default: **5 concurrent requests** with 0.5s delay between requests.

To adjust, edit `main.py` (line ~180):

```python
# Adjust concurrency
semaphore = asyncio.Semaphore(5)  # Change number

# Adjust delay
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
  "openai_api_configured": true
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
- **AI**: OpenAI GPT-4o API with **Web Search**
- **Data Processing**: Pandas
- **File Handling**: openpyxl, xlrd
- **Async Processing**: asyncio
- **Frontend**: HTML/CSS/JavaScript (vanilla)

### Web Search Integration

This tool leverages OpenAI's **built-in web search capabilities** to find real-time, accurate Facebook URLs. The AI model:
- ✅ Actually searches the web (site:facebook.com)
- ✅ Returns current, active Facebook pages
- ✅ Validates location matches
- ✅ Distinguishes between pages and groups
- ✅ Provides confidence scores based on match quality

**📖 For detailed information about how web search works, see [WEB_SEARCH_GUIDE.md](WEB_SEARCH_GUIDE.md)**

## 💰 Cost Estimation

Using **GPT-4o** (recommended for web search):
- ~$2.50 per million input tokens
- ~$10.00 per million output tokens

**Estimated cost per business**: ~$0.01-0.02 (1-2 cents with web search)

For **100 businesses**: ~$1-2
For **1000 businesses**: ~$10-20

**Note**: Web search functionality uses more tokens but provides significantly more accurate, real-time results. The model actually searches Facebook to find current URLs rather than relying on training data.

## ⚠️ Important Notes

1. **API Key Security**: Never commit your `.env` file or share your API key
2. **Rate Limits**: OpenAI has rate limits based on your account tier
3. **Search Accuracy**: Results depend on OpenAI's search capabilities and may not be 100% accurate
4. **Manual Review**: Always review low-confidence results manually
5. **Facebook Changes**: Facebook URL structures may change over time

## 🐛 Troubleshooting

### "OPENAI_API_KEY not set" warning

- Make sure you created a `.env` file with your API key
- Or set the environment variable before running the script

### "Rate limit exceeded" error

- Your OpenAI account has reached its rate limit
- Reduce concurrency in `main.py` (line ~180)
- Increase delay between requests

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

**Made with ❤️ using OpenAI API and FastAPI**

