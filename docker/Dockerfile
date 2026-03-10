FROM registry.gitlab.com/octopus-code/octopus:latest

USER root

# Install python and networking tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
RUN pip3 install --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple mcp pydantic Jinja2 numpy xarray netCDF4 uvicorn starlette

WORKDIR /workspace
# Copy server.py into image
COPY workspace/server.py /workspace/server.py

EXPOSE 8000

CMD ["python3", "server.py"]
