FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/bookkeeper \
    LOCAL_BOOKKEEPER_HOST=0.0.0.0 \
    LOCAL_BOOKKEEPER_PORT=8765 \
    LOCAL_BOOKKEEPER_CONFIG=/data/config/settings.json \
    LOCAL_BOOKKEEPER_DATA=/data \
    LOCAL_BOOKKEEPER_BOOKS_DIR="/data/profiles/My books" \
    LOCAL_BOOKKEEPER_STORAGE_ROOT=/data

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 bookkeeper \
    && useradd --uid 10001 --gid bookkeeper --create-home bookkeeper \
    && mkdir -p /data/config /data/profiles \
    && chown -R bookkeeper:bookkeeper /data

COPY server.py workspace_store.py statement_import.py reports.py backup.py \
    categorization.py credits.py source_archive.py import_evidence.py automation.py consistency.py review_batches.py rule_library.py ./
COPY index.html app.js profile_ui.js setup.js batch_selection.js categorize.js \
    source.js credits.js automation.js suggested_batches.js rule_library.js ./
COPY styles.css setup.css categorize.css source.css credits.css automation.css ./

USER bookkeeper
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4).close()"
CMD ["python", "-u", "server.py"]
