#!/bin/bash
echo "=== AI Signal Backend ==="
echo "Python: $(python --version)"
echo "Dir: $(pwd)"

echo ""
echo "=== Import check ==="
python -c "
import traceback, sys
checks = [
    ('fastapi', 'fastapi'),
    ('aiosqlite', 'aiosqlite'),
    ('aiohttp', 'aiohttp'),
    ('apscheduler', 'apscheduler'),
    ('feedparser', 'feedparser'),
    ('database', 'database'),
    ('news_fetcher', 'news_fetcher'),
    ('summarizer', 'summarizer'),
    ('emailer', 'emailer'),
    ('models', 'models'),
    ('routers.news', 'routers.news'),
    ('routers.users', 'routers.users'),
    ('routers.config', 'routers.config'),
    ('main app', 'main'),
]
ok = True
for label, mod in checks:
    try:
        __import__(mod)
        print(f'  OK   {label}')
    except Exception as e:
        print(f'  FAIL {label}: {e}')
        traceback.print_exc()
        ok = False
if not ok:
    sys.exit(1)
print('All imports OK')
" 2>&1

if [ $? -ne 0 ]; then
    echo "Import check failed — aborting"
    exit 1
fi

echo ""
echo "=== Starting server ==="
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
