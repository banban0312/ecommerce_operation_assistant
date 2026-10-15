# 从官方 uv 镜像复制安装器，Python 运行阶段保持精简。
FROM ghcr.io/astral-sh/uv:0.12.7 AS uv
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
# 使用锁文件安装生产依赖；构建时不安装开发工具和项目本身。
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir /app/uploads \
    && chown app:app /app/uploads
# 复制运行所需源码和迁移文件后，以非 root 用户运行服务。
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
