# Image sandbox chạy script pytest/Playwright do người dùng viết. Không chứa secret hay mã của máy chủ chính,
# ngoài omnitest-adapters (chỉ để chạy proxy kiểm soát mạng).
# Build từ thư mục gốc repo:  docker build -f infra/docker/sandbox.Dockerfile -t omnitest-sandbox:latest .
# Mạng doanh nghiệp có proxy TLS riêng: thêm  --secret id=extra_ca,src=/duong-dan/ca.crt
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

COPY adapters /tmp/build/adapters
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install --no-cache-dir --break-system-packages \
        playwright==1.63.0 pytest==9.1.1 pytest-playwright==0.10.0 pytest-base-url==2.1.0 httpx==0.28.1 \
        /tmp/build/adapters \
    && rm -rf /tmp/build

# Người dùng không root cố định; thư mục socket thuộc người dùng này (Docker sao chép quyền sang volume mới).
RUN useradd --uid 10001 --create-home --home-dir /home/sandbox --shell /usr/sbin/nologin sandbox \
    && mkdir -p /run/omnitest && chown 10001:10001 /run/omnitest && chmod 700 /run/omnitest
COPY infra/docker/sandbox/bootstrap.py infra/docker/sandbox/proxy_main.py \
     infra/docker/sandbox/conftest.py infra/docker/sandbox/pytest.ini /opt/omnitest/
USER 10001:10001
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENTRYPOINT ["python", "/opt/omnitest/bootstrap.py"]
