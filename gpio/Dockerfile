# syntax=docker/dockerfile:1

# Generated with docker init

# Comments are provided throughout this file to help you get started.
# If you need more help, visit the Dockerfile reference guide at
# https://docs.docker.com/engine/reference/builder/

ARG PYTHON_VERSION=3.12.4
FROM python:${PYTHON_VERSION}-slim AS base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# Leverage a bind mount to requirements.txt to avoid having to copy them into
# into this layer.
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gcc
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install --break-system-packages -r requirements.txt

# Copy the source code into the container.
COPY . .

RUN chmod 755 gpio_to_timestamps.py

# Expose the port that the application listens on.
#EXPOSE 8090

# Run the application.
CMD ["python", "gpio_to_timestamps.py"]
