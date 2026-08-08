FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NLTK_DATA=/opt/nltk_data

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-download the NLTK corpora used by nodes.py so cold starts need no network
# and no writable HOME. (Embeddings are served by the HF Inference API, so there
# is no local model to bake in.)
RUN python -m nltk.downloader -d /opt/nltk_data stopwords punkt punkt_tab

COPY . .

EXPOSE 8000

# Render (and most PaaS hosts) inject $PORT.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
