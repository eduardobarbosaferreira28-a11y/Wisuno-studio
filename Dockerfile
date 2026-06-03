FROM python:3.12-slim

# Prevent Python from buffering stdout and pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1

WORKDIR /app

# Install system dependencies
# ffmpeg is needed for video processing
# imagemagick is needed for moviepy/hyperframes text/image rendering
# curl is needed to install Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install hyperframes globally
RUN npm install -g hyperframes

# Fix ImageMagick policy to allow text/rendering if needed (common moviepy issue)
# (In debian 11+, ImageMagick disables some ghostscript fonts/paths by default. We remove the policy file if it exists)
RUN rm -f /etc/ImageMagick-6/policy.xml

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements and install
# 1. Main requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Studio backend requirements
COPY studio/backend/requirements_studio.txt studio/backend/
RUN pip install --no-cache-dir -r studio/backend/requirements_studio.txt

# 3. Video-use requirements (it's a local package/pyproject.toml)
COPY studio/repos/video-use/pyproject.toml studio/repos/video-use/
# Install dependencies from pyproject.toml directly using pip
RUN pip install --no-cache-dir studio/repos/video-use/

# Install Playwright Chromium (with OS dependencies)
# We need to run `playwright install-deps` which installs apt packages, 
# then `playwright install chromium`
RUN playwright install-deps && playwright install chromium

# Copy the rest of the application code
COPY . .

# Ensure output directories exist
RUN mkdir -p output/carousel output/video output/audio output/temp

# Expose the API port
EXPOSE 8000

# Start Uvicorn directly
CMD ["uvicorn", "studio.backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
