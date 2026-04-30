FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create an unprivileged user to run the service. Avoid running as root.
RUN useradd -u 1001 -m app

WORKDIR /app

COPY --chown=app:app requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY --chown=app:app app/ /app/app/

# Ensure runtime dir exists and is writable by the app user (api_token.txt
# is written here on first boot).
RUN mkdir -p /app/runtime && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
