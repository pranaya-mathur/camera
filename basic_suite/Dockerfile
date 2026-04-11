# Stage 1: Build the UI
FROM node:18-slim AS ui-builder
WORKDIR /ui
COPY ui/package*.json ./
RUN npm install
COPY ui ./
RUN npm run build

# Stage 2: Final image
FROM python:3.10-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY models/requirements.txt /tmp/models-requirements.txt
COPY backend/requirements.txt /tmp/backend-requirements.txt
# CPU-only PyTorch first (avoids default CUDA wheels; matches DEVICE=cpu pilot on GCP).
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN grep -vE '^(torch|torchvision)$' /tmp/models-requirements.txt > /tmp/models-no-torch.txt && \
    pip install --no-cache-dir -r /tmp/models-no-torch.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt

COPY models /app/models
COPY pipeline /app/pipeline
COPY backend /app/backend
COPY basic_suite /app/basic_suite
# Copy built UI from stage 1
COPY --from=ui-builder /ui/dist /app/basic_suite/ui/dist

RUN bash /app/models/setup_models.sh

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
# Pilot / container defaults (override at runtime as needed).
ENV DEVICE=cpu
ENV BASIC_SUITE_API_HOST=0.0.0.0
ENV BASIC_SUITE_DATA_DIR=/data/basic_suite

RUN mkdir -p /data/basic_suite

EXPOSE 8000

CMD ["python3", "basic_suite/run_basic_suite.py"]
