FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
# psycopg2-binary publishes no armv7l wheel, so on 32-bit Raspberry Pi OS pip
# falls back to a source build - which needs a compiler and the libpq headers.
# Without these the build fails with "Getting requirements to build wheel did
# not run successfully". No-op on amd64/arm64, where the wheel is used.
RUN apt-get update \
# libc6-dev is required explicitly: --no-install-recommends stops gcc pulling it
# in, and without it the compile dies on "Python.h: fatal error: stdlib.h: No
# such file or directory".
 && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev \
 && pip install --no-cache-dir -r requirements.txt \
 && rm -rf /var/lib/apt/lists/*
COPY . .
CMD ["python", "main.py"]
