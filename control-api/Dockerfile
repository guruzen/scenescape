FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libegl1 \
       libgl1 \
       libglib2.0-0 \
       libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home app

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY scenescape_api ./scenescape_api
COPY model_configs ./model_configs
USER 1000:1000
ENTRYPOINT ["python","-m","scenescape_api.cli"]
CMD ["serve"]
