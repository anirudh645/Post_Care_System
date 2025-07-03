@echo off
echo ======================================
echo Cardiac Post-Care App - Setup Script
echo ======================================
echo.

echo 1. Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo 2. Setting up environment file...
if not exist .env (
    if exist .env.example (
        copy .env.example .env
        echo ✅ Created .env file from template
    ) else (
        echo # Environment variables for Cardiac Post-Care Assessment App > .env
        echo HUGGINGFACE_API_TOKEN=your_token_here >> .env
        echo DB_HOST=localhost >> .env
        echo DB_USER=root >> .env
        echo DB_PASSWORD= >> .env
        echo DB_NAME=post_care_db >> .env
        echo ✅ Created .env file with defaults
    )
    echo.
    echo ⚠️  IMPORTANT: Edit .env file and add your API token
    echo    Get token at: https://huggingface.co/settings/tokens
) else (
    echo ✅ .env file already exists
)

echo.
echo 3. Testing configuration...
python test_env_config.py

echo.
echo ======================================
echo Setup completed! 
echo.
echo Next steps:
echo 1. Edit .env file with your API token
echo 2. Start MySQL server
echo 3. Run: streamlit run post_care_app.py
echo ======================================
pause
