FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Bake model/corpus caches into the image so cold starts need no network
    # and no writable HOME.
    HF_HOME=/opt/hf \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf \
    NLTK_DATA=/opt/nltk_data

WORKDIR /app

# Install CPU-only torch first. The default PyPI wheel drags in ~3GB of CUDA
# libraries that are dead weight on a CPU host.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-download the embedding model and the NLTK corpora used by nodes.py.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" \
 && python -m nltk.downloader -d /opt/nltk_data stopwords punkt punkt_tab

COPY . .

# Persistent disk mount point for the SQLite database.
ENV DB_PATH=/var/data/jds.db

EXPOSE 8000

# Render (and most PaaS hosts) inject $PORT.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
