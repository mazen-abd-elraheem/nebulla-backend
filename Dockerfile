# ==============================================================================
# Nebula Backend - High-Performance GPU Dockerfile (CUDA 12.4 + Python 3.12)
# ==============================================================================
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /app

# 1. Install system dependencies, audio libraries, and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    curl \
    git \
    build-essential \
    ffmpeg \
    libsndfile1 \
    libsndfile1-dev \
    portaudio19-dev \
    libasound2-dev \
    pkg-config \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    python3.12-distutils \
    && rm -rf /var/lib/apt/lists/*

# 2. Configure Python 3.12 as the primary python environment
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# 3. Upgrade pip and build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 4. Install PyTorch with native CUDA 12.4 support first (cached layer)
RUN pip install --no-cache-dir \
    torch==2.6.0+cu124 \
    torchvision==0.21.0+cu124 \
    torchaudio==2.6.0+cu124 \
    --index-url https://download.pytorch.org/whl/cu124

# 5. Install application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy application source code
COPY . .

# 7. Create storage and artifact directories
RUN mkdir -p logs data/voice_samples data/embeddings models

# 8. Expose Nebula Backend API port
EXPOSE 8000

# 9. Healthcheck to verify service availability
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/diagnostics/status || exit 1

# 10. Run FastAPI application via Uvicorn (supports Railway $PORT dynamic binding)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
