# A single Dockerfile with separate targets for the web app and Telegram bot.
FROM python:3.12-slim AS bot
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY bot/requirements.txt /app/bot/requirements.txt
RUN pip install --no-cache-dir -r /app/bot/requirements.txt
COPY bot/ /app/bot/
COPY scripts/ /app/scripts/
RUN useradd --create-home --uid 10001 learner \
    && chown -R learner:learner /app
USER learner
CMD ["python", "-m", "bot.main"]

FROM nginx:1.27-alpine AS app
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY web/ /usr/share/nginx/html/web/
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/health || exit 1
