FROM mambaorg/micromamba

WORKDIR /app

COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yaml ./environment.yaml
RUN micromamba install -y -n base -f ./environment.yaml && \
    micromamba clean --all --yes

ARG MAMBA_DOCKERFILE_ACTIVATE=1
COPY --chown=$MAMBA_USER:$MAMBA_USER app .
RUN chmod ug+rwx .

RUN python download_kernels.py
RUN openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365 -subj "$(cat ssl.subj)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--ssl-keyfile", "/app/key.pem", "--ssl-certfile", "/app/cert.pem"]
