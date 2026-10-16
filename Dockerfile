FROM python:3.12-slim
RUN useradd --create-home --uid 10001 dojo
WORKDIR /app
COPY . /app
USER dojo
ENTRYPOINT ["python", "run.py"]
