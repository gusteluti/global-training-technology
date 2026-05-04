#!/bin/bash
# Quick start script for Windows PowerShell and macOS/Linux

# Check Python version
echo "🐍 Checking Python version..."
python --version

# Create and activate virtual environment
echo "📦 Creating virtual environment..."
if command -v python3 &> /dev/null; then
    python3 -m venv venv
else
    python -m venv venv
fi

# Activate venv
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    echo "🪟 Activating venv for Windows..."
    source venv/Scripts/activate
else
    echo "🐧 Activating venv for macOS/Linux..."
    source venv/bin/activate
fi

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Create .env file
echo "📝 Setting up environment variables..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ .env file created from template"
    echo "⚠️  Please edit .env and add your GROQ_API_KEY"
else
    echo "✅ .env already exists"
fi

echo ""
echo "==========================================="
echo "✅ Setup complete!"
echo "==========================================="
echo ""
echo "📝 Next steps:"
echo "1. Edit .env and add your GROQ_API_KEY"
echo "2. Run: python app.py"
echo "3. Test API: python test_api.py"
echo ""
echo "Get your Groq API key at: https://console.groq.com"
echo ""
