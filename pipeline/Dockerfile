FROM python:3.10-slim
WORKDIR /app
COPY models/requirements.txt /tmp/models-requirements.txt
RUN pip install --no-cache-dir -r /tmp/models-requirements.txt
COPY pipeline /app
COPY models /app/models
