FROM python:3.12-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libzbar0 libatomic1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.in /tmp/requirements.in
RUN python - <<'PY'
from pathlib import Path
text = Path('/tmp/requirements.in').read_text(encoding='utf-8-sig')
text = '\n'.join(line for line in text.splitlines() if not line.startswith(('pywebview', 'pystray', 'PyAutoGUI')))
text = text.replace('opencv-python==', 'opencv-python-headless==').replace('ddddocr>=1.4.7', 'ddddocr==1.5.6')
Path('/tmp/android-requirements.txt').write_text(text)
PY
RUN pip install --no-cache-dir -r /tmp/android-requirements.txt && pip uninstall -y opencv-python && pip install --no-cache-dir --force-reinstall --no-deps opencv-python-headless==4.9.0.80 && pip install --no-cache-dir --no-deps pnnx==20260526
RUN mkdir -p /mower /mower-data /bridge /host-dev /host-proc && chmod 1777 /tmp
WORKDIR /mower
