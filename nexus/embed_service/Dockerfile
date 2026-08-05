# 임베딩 사이드카 (SPEC-nexus-kure-embedding-swap §4.1).
#
# **앱 이미지와 별개다.** torch 는 여기 있고 nexus 앱에는 없다 — 평가 SPEC 이 약속한 격리를
# 유지하는 방법이 이 파일이다(앱은 HTTP 로만 말한다). tests/test_ko_eval_deferral.py 가 그 약속을
# 지킨다: 앱의 의존성 집합에 torch/sentence-transformers 가 들어오면 실패한다.
FROM python:3.11-slim

# CPU 휠을 쓴다. GPU 는 처리량 문제이지 실현 가능성 문제가 아니다 (질의 101ms/CPU 실측).
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1
# transformers·tokenizers 도 못박는다. 길이검사 사본(SPEC-nexus-embed-tokenizer-race §3)의
# 안전성은 `copy.deepcopy` 가 **별개의 Rust 토크나이저**를 만든다는 성질에 기대고, 그 성질은
# 이 두 라이브러리의 것이다 — 안 박으면 이미지 재빌드가 수정의 전제를 조용히 갈아치운다.
# 측정에 쓴 조합: tokenizers 0.22.2 · transformers 4.57.6 · sentence-transformers 3.3.1.
RUN pip install --no-cache-dir \
    "sentence-transformers==3.3.1" \
    "transformers==4.57.6" \
    "tokenizers==0.22.2" \
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
