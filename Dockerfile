FROM python:3.12-slim

# Prevent Python from buffering stdout and pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1

# Make pip resilient to slow/flaky PyPI mirrors (Railway builders occasionally
# time out fetching package metadata — the default 15s read timeout then cascades
# into a bogus "ResolutionImpossible" during backtracking).
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_RETRIES=8

# Memory optimization for 2GB Render Standard plan
ENV MALLOC_ARENA_MAX=2
ENV PLAYWRIGHT_CHROMIUM_DISABLE_GPU=1
ENV NODE_OPTIONS="--max-old-space-size=256"

WORKDIR /app

# Install system dependencies
# ffmpeg is needed for video processing
# imagemagick is needed for moviepy/hyperframes text/image rendering
# curl is needed to install Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    fonts-liberation \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install hyperframes globally — PINNED. An unpinned install pulls whatever is
# latest at build time; a newer build that seeks GSAP timelines by progress
# (instead of absolute seconds) stretches the karaoke captions across the whole
# clip, so they drift slower and slower behind the speaker. 0.7.18 is verified
# to seek by absolute seconds. Bump deliberately, never accidentally.
RUN npm install -g hyperframes@0.7.18

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

# Start Uvicorn using the dynamic PORT environment variable (default to 8000)
CMD ["sh", "-c", "uvicorn studio.backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
