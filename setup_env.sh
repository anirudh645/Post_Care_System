#!/bin/bash
echo "======================================"
echo "Cardiac Post-Care App - Setup Script"
echo "======================================"
echo

echo "1. Installing Python dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies"
    exit 1
fi

echo
echo "2. Setting up environment file..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Created .env file from template"
    else
        cat > .env << EOF
# Environment variables for Cardiac Post-Care Assessment App
HUGGINGFACE_API_TOKEN=your_token_here
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=
DB_NAME=post_care_db
EOF
        echo "✅ Created .env file with defaults"
    fi
    echo
    echo "⚠️  IMPORTANT: Edit .env file and add your API token"
    echo "   Get token at: https://huggingface.co/settings/tokens"
else
    echo "✅ .env file already exists"
fi

echo
echo "3. Testing configuration..."
python test_env_config.py

echo
echo "======================================"
echo "Setup completed!"
echo
echo "Next steps:"
echo "1. Edit .env file with your API token"
echo "2. Start MySQL server"
echo "3. Run: streamlit run post_care_app.py"
echo "======================================"
