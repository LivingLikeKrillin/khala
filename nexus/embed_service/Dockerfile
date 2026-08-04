# 임베딩 사이드카 (SPEC-nexus-kure-embedding-swap §4.1).
#
# **앱 이미지와 별개다.** torch 는 여기 있고 nexus 앱에는 없다 — 평가 SPEC 이 약속한 격리를
# 유지하는 방법이 이 파일이다(앱은 HTTP 로만 말한다). tests/test_ko_eval_deferral.py 가 그 약속을
# 지킨다: 앱의 의존성 집합에 torch/sentence-transformers 가 들어오면 실패한다.
FROM python:3.11-slim

# CPU 휠을 쓴다. GPU 는 처리량 문제이지 실현 가능성 문제가 아니다 (질의 101ms/CPU 실측).
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1
RUN pip install --no-cache-dir \
    "sentence-transformers==3.3.1" \
    "fastapi==0.115.6" \
    "uvicorn[standard]==0.34.0" \
    "pydantic==2.10.4"

WORKDIR /app
COPY app.py /app/app.py

# 모델은 빌드 때 굽지 않는다 — 리비전을 바꾸려고 이미지를 다시 굽는 것은 롤백을 느리게 만든다.
# 대신 캐시 볼륨에 받아 두고 리비전을 환경변수로 못박는다.
ENV HF_HOME=/hf
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
