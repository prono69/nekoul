FROM python:3.10-bullseye
 
# Set timezone
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
 
# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libnss3 \
    ca-certificates \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libdrm2 \
    libgbm1 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxtst6 \
    neofetch \
    git \
    curl \
    wget \
    jq \
    python3-dev \
    mediainfo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
    
    
# Manual FFmpeg installation (preserved as requested)
RUN wget -q https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz \
    && wget -q https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz.md5 \
    && md5sum -c ffmpeg-git-amd64-static.tar.xz.md5 \
    && tar xf ffmpeg-git-amd64-static.tar.xz \
    && mv ffmpeg-git-*-amd64-static/ffmpeg ffmpeg-git-*-amd64-static/ffprobe /usr/local/bin/ \
    && rm -rf ffmpeg-git-* ffmpeg-git-amd64-static.tar.xz*
    
 
 
# Create user with UID 1000 (Hugging Face requirement)
RUN useradd -m -u 1000 user
 
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PIP_CACHE_DIR=/home/user/.cache/pip
 
# Set working directory (creates /home/user/app automatically)
WORKDIR $HOME/app
 
# Create cache directory for pip (only .cache, since WORKDIR already creates /app)
RUN mkdir -p $HOME/.cache && chmod -R 777 $HOME/.cache
RUN chown -R 1000:0 $HOME/app && \
    chmod -R 755 $HOME/app
 
# Copy requirements first to leverage Docker cache
COPY --chown=user requirements.txt .
RUN pip install --upgrade pip setuptools \
    && pip install -r requirements.txt
 
 
# Copy application code
COPY --chown=user . .
 
RUN python3 -m pip check yt-dlp
 
EXPOSE 7860
 
CMD ["bash", "-c", "python3 server.py & python3 bot.py"]