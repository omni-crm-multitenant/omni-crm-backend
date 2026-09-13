FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN addgroup --system omni && adduser --system --ingroup omni omni
COPY requirements.lock .
RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --upgrade --no-cache-dir pip \
    && python -m pip uninstall --yes msgpack setuptools \
    && rm -rf /usr/local/lib/python3.13/site-packages/msgpack* /usr/local/lib/python3.13/site-packages/setuptools* \
    && python -m pip install --no-cache-dir msgpack==1.2.1 setuptools==83.0.0 \
    && python -m pip install --upgrade --no-cache-dir --requirement requirements.lock \
    && python -c "import importlib.metadata as m; assert m.version('msgpack') == '1.2.1'; assert m.version('setuptools') == '83.0.0'"
COPY . .
RUN chown -R omni:omni /app
USER omni
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

