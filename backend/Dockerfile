FROM python:3.11-slim

WORKDIR /app

# 清除旧源，使用清华镜像
RUN rm -f /etc/apt/sources.list && \
    echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian/ trixie main' > /etc/apt/sources.list && \
    echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian-security/ trixie-security main' >> /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]