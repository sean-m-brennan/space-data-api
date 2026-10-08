FROM mambaorg/micromamba

WORKDIR /app

COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml ./environment.yml
RUN micromamba install -y -n base -f ./environment.yml && \
    micromamba clean --all --yes

ARG MAMBA_DOCKERFILE_ACTIVATE=1
COPY --chown=$MAMBA_USER:$MAMBA_USER app .
RUN chmod ug+rwx .

# Optionally bake the ~1.7 GB SPICE kernels into the image. Default on, so the
# standalone image and local_deploy.sh behave exactly as before. The Tilt/compose
# dev stack passes DOWNLOAD_KERNELS=0 and bind-mounts a persistent /app/kernels
# instead, so image rebuilds don't re-download (download_kernels.py is idempotent
# at runtime: _fetch skips kernels already present).
ARG DOWNLOAD_KERNELS=1
RUN if [ "$DOWNLOAD_KERNELS" = "1" ]; then python download_kernels.py; fi
RUN openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365 -subj "$(cat ssl.subj)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--ssl-keyfile", "/app/key.pem", "--ssl-certfile", "/app/cert.pem"]
