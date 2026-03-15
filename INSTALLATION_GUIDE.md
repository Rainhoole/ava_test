# Installation Guide

## Important Requirements

### Python Version
**fastmcp requires Python 3.10 or higher**

Check your Python version:
```bash
python --version
# or
python3 --version
```

If you have Python < 3.10, you need to upgrade first.

## Installation Options

### Option 1: Using UV (Recommended by fastmcp)
```bash
# Install uv first
curl -LsSf https://astral.sh/uv/install.sh | sh

# Then install fastmcp
uv pip install fastmcp
```

### Option 2: Using pip with Python 3.10+
```bash
# Make sure you're using Python 3.10+
python3.10 -m pip install fastmcp

# Or if python3 points to 3.10+
python3 -m pip install -r requirements.txt
```

### Option 3: Using conda/pyenv
```bash
# Create a Python 3.10+ environment
conda create -n mcp python=3.10
conda activate mcp

# Then install
pip install -r requirements.txt
```

## Troubleshooting

### Error: No matching distribution found
This usually means:
1. Your Python version is < 3.10
2. Network/proxy issues

Run the diagnostic script:
```bash
python diagnose_pip.py
```

### Manual Installation
If automated installation fails:
```bash
# Install dependencies one by one
pip install fastmcp==2.10.2
pip install uvicorn[standard]
pip install sse-starlette
pip install openai
pip install notion-client
pip install requests
pip install firecrawl-py
pip install python-dotenv
```

## Verify Installation
```bash
# Test imports
python -c "import fastmcp; print('fastmcp installed successfully')"
```