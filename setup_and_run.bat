@echo off
echo ========================================
echo Facebook URL Search Tool - Setup
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from https://www.python.org/
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [2/3] Checking for API key...
if not exist .env (
    echo WARNING: .env file not found!
    echo.
    echo Please create a .env file with your OpenAI API key:
    echo OPENAI_API_KEY=your_api_key_here
    echo.
    echo Or set it as environment variable before running.
    echo.
    set /p APIKEY="Enter your OpenAI API key now (or press Enter to skip): "
    if not "!APIKEY!"=="" (
        echo OPENAI_API_KEY=!APIKEY! > .env
        echo .env file created successfully!
    )
)

echo.
echo [3/3] Starting server...
echo.
echo ========================================
echo Server will start at: http://localhost:8000
echo Press Ctrl+C to stop the server
echo ========================================
echo.

python main.py

