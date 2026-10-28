FROM python:3.11-slim-bookworm
LABEL authors="dante.dumon"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git unixodbc-dev freetds-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
# These jobs run without a display. The legacy GUI examples need PySimpleGUI
# separately. Keep pkg_resources/distutils available for the legacy dependencies.
RUN sed '/^PySimpleGUI/d; /^setuptools/d' /tmp/requirements.txt > /tmp/requirements-container.txt \
    && pip install --no-cache-dir 'setuptools==80.9.0' wheel \
    && pip install --no-cache-dir -r /tmp/requirements-container.txt

COPY . /app
RUN mkdir -p /output /app/dbworks/database
WORKDIR /output

CMD ["python", "-m", "eurobisqc.examples.process_list", "--providers", "1476"]
