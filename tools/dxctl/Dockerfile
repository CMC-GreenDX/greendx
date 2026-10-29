FROM python:3.13.16-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /work
COPY requirements.txt /opt/dxctl/requirements.txt
RUN pip install -r /opt/dxctl/requirements.txt
COPY dxctl.py /opt/dxctl/dxctl.py
ENTRYPOINT ["python", "/opt/dxctl/dxctl.py"]
