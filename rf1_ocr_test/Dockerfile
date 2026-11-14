FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pil tesseract-ocr tesseract-ocr-eng tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY run.py checks.py layout.py /
CMD ["/usr/bin/python3", "-u", "/run.py"]
