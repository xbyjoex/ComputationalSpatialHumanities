FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg binary and shapely
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.scheduler"]
