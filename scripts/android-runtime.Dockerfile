FROM python:3.12-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libzbar0 libatomic1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.in /tmp/requirements.in
COPY docker/gen_server_requirements.py /tmp/gen_server_requirements.py
COPY scripts/prune_opencv.py /tmp/prune_opencv.py
RUN python /tmp/gen_server_requirements.py /tmp/requirements.in /tmp/android-requirements.txt \
    && pip install --no-cache-dir -r /tmp/android-requirements.txt \
    && python -m pip check \
    && python /tmp/prune_opencv.py \
    && pip install --no-cache-dir --no-deps pnnx==20260526
RUN mkdir -p /mower /mower-data /bridge /host-dev /host-proc && chmod 1777 /tmp
WORKDIR /mower
