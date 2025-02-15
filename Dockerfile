# Use an official Python runtime as a parent image
FROM python:3.10-bullseye

# Set timezone
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Set HOME to /app so that user-specific directories (.config, .cache, .local) are under /app
ENV HOME=/app
# Add the local bin directory to PATH so that installed scripts are available
ENV PATH="/app/.local/bin:${PATH}"

# Install OS-level dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        neofetch \
        libnss3 \
        libx11-xcb1 \
        libxcursor1 \
        libxi6 \
        libgtk-3-0 \
        libnspr4 \
        libdbus-1-3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libatspi2.0-0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        git \
        curl \
        wget \
        zip \
        jq \
        python3-dev \
        p7zip-full \
        mediainfo && \
    apt-get autoremove --purge -y && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements.txt first for caching purposes
COPY requirements.txt .

# Ensure the system site-packages directory is writable by user 1000
RUN chown -R 1000:0 /usr/local/lib/python3.10/site-packages && \
    chmod -R 777 /usr/local/lib/python3.10/site-packages && \
    pip install --upgrade pip setuptools && \
    pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set permissions on /app and create/configure the cache, config, and local directories under $HOME
RUN chown -R 1000:0 /app && chmod -R 777 /app && \
    mkdir -p $HOME/.cache $HOME/.config $HOME/.local && \
    chown -R 1000:0 $HOME/.cache $HOME/.config $HOME/.local && \
    chmod -R 777 $HOME/.cache $HOME/.config $HOME/.local

# (Optional) Verify dependencies for yt-dlp if needed
RUN python -m pip check yt-dlp

# Download, verify, extract, and clean up ffmpeg installation
RUN wget https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz && \
    wget https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz.md5 && \
    md5sum -c ffmpeg-git-amd64-static.tar.xz.md5 && \
    tar xvf ffmpeg-git-amd64-static.tar.xz && \
    mv ffmpeg-git*/ffmpeg /usr/local/bin/ && \
    mv ffmpeg-git*/ffprobe /usr/local/bin/ && \
    rm -rf ffmpeg-git* ffmpeg-git-amd64-static.tar.xz ffmpeg-git-amd64-static.tar.xz.md5


# Expose the application port
EXPOSE 7860

# Start the application via the startup script
CMD ["bash", "-c", "python3 server.py & python3 bot.py"]