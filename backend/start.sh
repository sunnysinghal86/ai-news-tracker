#!/bin/bash
set -e

echo "=== Starting AI Signal Backend ==="
echo "Python: $(python --version)"
echo "Working dir: $(pwd)"
echo "Files: $(ls)"

echo ""
echo "=== Checking imports ==="
python -c "
import sys
try:
    import fastapi; print('OK fastapi', fastapi.__version__)
    import aiosqlite; print('OK aiosqlite')
    import aiohttp; print('OK aiohttp')
    import apscheduler; print('OK apscheduler')
    import feedparser; print('OK feedparser')
    print('--- app modules ---')
    import database; print('OK database')
    import news_fetcher; print('OK news_fetcher')
    import summarizer; print('OK summarizer')
    import emailer; print('OK emailer')
    import models; print('OK models')
    from routers import news, users, config; print('OK routers')
    import main; print('OK main')
    print('All imports OK')
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
" 2>&1

echo ""
echo "=== Launching uvicorn ==="
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" 2>&1
