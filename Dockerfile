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
 
# Set environment variables for the non-root user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
 
# Set working directory (creates /home/user/app automatically)
WORKDIR $HOME/app
 
# (Optional) If you want to disable pip caching entirely, you can skip creating the cache directory.
# Otherwise, you could fix its permissions—but here we opt to disable caching.
RUN mkdir -p $HOME/.cache

 
# Adjust ownership/permissions for the app directory (and /usr if needed)
RUN chown -R 1000:0 $HOME/app $HOME/.cache /usr && \
    chmod -R 777 $HOME/app /usr $HOME/.cache
 
# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools \
    && pip install --no-cache-dir -r requirements.txt
 
# Copy application code
COPY . .
 
RUN python3 -m pip check yt-dlp
 
EXPOSE 7860

CMD ["bash", "-c", "python3 server.py & python3 bot.py"]
