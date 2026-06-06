# ─── ChronoGen — Production Dockerfile ───────────────────────────────────────
# Multi-stage build: keeps the final image lean.

# Stage 1 — dependency builder
FROM python:3.11-slim AS builder
WORKDIR /install

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install/deps --no-cache-dir -r requirements.txt


# Stage 2 — runtime image
FROM python:3.11-slim AS runtime
LABEL maintainer="ChronoGen Team"
LABEL description="AI-powered timetable scheduling system"

# Non-root user for security
RUN addgroup --system chronogen && adduser --system --ingroup chronogen chrono

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install/deps /usr/local

# Copy application source
COPY frontend/ ./frontend/
COPY data/      ./data/
COPY main.py   .

# Ensure data directory is writable
RUN chown -R chrono:chronogen /app

USER chrono

# Expose Flask port
EXPOSE 5000

# Set production environment variables (override at runtime)
ENV FLASK_ENV=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SECRET_KEY=change-me-in-production

# Launch with gunicorn + eventlet for SocketIO support
CMD ["python", "-m", "gunicorn", \
     "--worker-class", "eventlet", \
     "--workers", "1", \
     "--bind", "0.0.0.0:5000", \
     "--chdir", "frontend", \
     "app:app"]
