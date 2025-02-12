FROM python:3.9-slim

WORKDIR /app
WORKDIR /.cache

RUN apt -qq update && \
    apt -qq install -y --no-install-recommends \
    curl \
    git \
    wget \
    jq \
    python3-dev \
    neofetch && \
    apt-get autoremove --purge -y && \
    apt-get clean && \
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
