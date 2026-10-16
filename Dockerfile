FROM python:3.12-slim
RUN useradd --create-home --uid 10001 dojo
WORKDIR /app
COPY dojo /app/dojo
USER dojo
ENTRYPOINT ["python", "-m", "dojo.docker_child"]
