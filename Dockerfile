# Use an official Python runtime as a parent image
FROM python:3.9.5-buster

# Set timezone
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app
WORKDIR /.cache
    
# Install dependencies
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

COPY . .
COPY requirements.txt .
RUN pip3 install --upgrade pip setuptools
RUN pip3 install -r requirements.txt

RUN chown -R 1000:0 .
RUN chmod 777 .
RUN chown -R 1000:0 /app
RUN chmod 777 /app
RUN chown -R 1000:0 /.cache
RUN chmod 777 /.cache

RUN python3 -m pip check yt-dlp

RUN wget https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz
RUN wget https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz.md5
RUN md5sum -c ffmpeg-git-amd64-static.tar.xz.md5
RUN tar xvf ffmpeg-git-amd64-static.tar.xz
RUN mv ffmpeg-git*/ffmpeg ffmpeg-git*/ffprobe /usr/local/bin/

EXPOSE 7860

CMD ["bash", "-c", "python3 server.py & python3 bot.py"]
