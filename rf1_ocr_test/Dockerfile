FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pil python3-websocket tesseract-ocr tesseract-ocr-eng tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY run.py app_channel.py consumption.py checks.py layout.py reminder.py settings.py panel.py i18n.py language.py transport.py notification_settings.py source_settings.py /
CMD ["/usr/bin/python3", "-u", "/run.py"]
