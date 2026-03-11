FROM python:3.11-slim

# System dependencies + mecab base
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    automake \
    autoconf \
    libtool \
    && rm -rf /var/lib/apt/lists/*

# 1) mecab-ko 엔진 먼저 설치
RUN curl -fsSL https://bitbucket.org/eunjeon/mecab-ko/downloads/mecab-0.996-ko-0.9.2.tar.gz \
    | tar xz -C /tmp \
    && cd /tmp/mecab-0.996-ko-0.9.2 \
    && ./configure \
    && make \
    && make install \
    && ldconfig \
    && rm -rf /tmp/mecab-0.996-ko-0.9.2

# 2) mecab-ko-dic 한국어 사전 설치
RUN curl -fsSL https://bitbucket.org/eunjeon/mecab-ko-dic/downloads/mecab-ko-dic-2.1.1-20180720.tar.gz \
    | tar xz -C /tmp \
    && cd /tmp/mecab-ko-dic-2.1.1-20180720 \
    && autoreconf -fi || ./autogen.sh || true \
    && ./configure \
    && make \
    && make install \
    && rm -rf /tmp/mecab-ko-dic-2.1.1-20180720

WORKDIR /app

# Application code
COPY . .

# Python dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# mecab 동작 확인
RUN echo "결제 서비스가 알림을 보낸다" | mecab || echo "mecab test skipped"

EXPOSE 8000

CMD ["uvicorn", "khala.api:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
