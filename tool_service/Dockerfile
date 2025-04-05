FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    python3-grpcio-tools \
    curl unzip chromium chromium-driver xvfb \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver
RUN CHROME_VERSION=$(chromium-browser --version | grep -oP '\d+\.\d+\.\d+') \
    && CHROME_DRIVER_VERSION=$(curl -sS "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION") \
    && wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip" \
    && unzip /tmp/chromedriver.zip -d /usr/bin \
    && chmod +x /usr/bin/chromedriver \
    && rm /tmp/chromedriver.zip

WORKDIR /app

COPY shared/proto/tool.proto ./proto/

RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/tool.proto

COPY tool_service/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN rm -rf ./proto

COPY tool_service/tool_service.py .

EXPOSE 50053
CMD ["python", "tool_service.py"]