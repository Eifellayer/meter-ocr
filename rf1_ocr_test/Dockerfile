FROM debian:bookworm-slim
ARG BUILD_VERSION
ENV BUILD_VERSION=${BUILD_VERSION}
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pil python3-websocket tesseract-ocr tesseract-ocr-eng tzdata fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY run.py app_channel.py consumption.py checks.py layout.py reminder.py settings.py auto_rules.py setup_store.py setup_flow.py status_view.py system_monitor.py background_view.py seven_segment.py read_plan.py idle_work.py panel.py i18n.py language.py transport.py notification_settings.py source_settings.py calibration.py meter_learning.py demo.py debug_log.py bug_report.py experiments.py glyph_match.py optimizer.py digit_library.py digit_templates.png /
COPY demo_images /demo_images
CMD ["/usr/bin/python3", "-u", "/run.py"]
