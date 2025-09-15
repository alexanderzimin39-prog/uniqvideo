# Python base image
FROM python:3.11-slim

# Install system dependencies (ffmpeg for moviepy)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Environment
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Expose the port used for health checks (Koyeb provides PORT env)
EXPOSE 8080

# Run bot
CMD ["python", "bot.py"]
