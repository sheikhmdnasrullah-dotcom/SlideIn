# Sink MX — synthesizes Gmail / Yahoo / Microsoft / Apple-like responses so the lab
# can measure shaping outcomes without touching the real Internet.
#
# Defaults: listen on :25, record every SMTP event, replay a configured scenario.

FROM python:3.12-alpine

RUN apk add --no-cache tini busybox-extras curl tcpdump
RUN pip install --no-cache-dir pyyaml aiohttp

WORKDIR /app

COPY app /app/app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]