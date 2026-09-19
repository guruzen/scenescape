FROM python:3.12-slim
RUN useradd --uid 1000 --create-home app
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY scenescape_api ./scenescape_api
USER 1000:1000
ENTRYPOINT ["python","-m","scenescape_api.cli"]
CMD ["serve"]
