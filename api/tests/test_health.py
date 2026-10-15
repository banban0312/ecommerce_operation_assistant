import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.api.routes import health as health_routes
from app.core.config import Settings
from app.main import app
from app.observability import JsonFormatter
from app.services import health


@pytest.fixture
def client():
    # 使用 FastAPI 测试客户端，并通过上下文管理器触发生命周期钩子。
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def healthy_dependencies(monkeypatch):
    # 默认模拟依赖健康，让单个用例只需覆盖正在验证的故障项。
    for name in ("check_database", "check_redis", "check_storage"):
        monkeypatch.setattr(health, name, lambda: None)


def test_liveness_does_not_require_dependencies(client, monkeypatch):
    # 数据库故障不能让进程存活检查失败。
    def unavailable():
        raise ConnectionError("unavailable")

    monkeypatch.setattr(health, "check_database", unavailable)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"service": "api", "status": "ok"}


def test_readiness_checks_all_dependencies(client, healthy_dependencies):
    # 就绪响应应包含每项依赖，且不能被缓存。
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert set(response.json()["checks"]) == {"database", "redis", "storage"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("dependency", ["check_database", "check_redis", "check_storage"])
def test_dependency_failure_is_503_without_secret_leak(
    client, monkeypatch, healthy_dependencies, dependency, capsys
):
    # 故障细节可以写入安全日志类型，但密码和密钥不能出现在响应或日志中。
    def unavailable():
        raise ConnectionError("mysql://user:PRIVATE_PASSWORD@mysql; key=PRIVATE_KEY")

    monkeypatch.setattr(health, dependency, unavailable)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"][dependency.removeprefix("check_")]["status"] == "unavailable"
    output = response.text + capsys.readouterr().err
    assert "PRIVATE_PASSWORD" not in output
    assert "PRIVATE_KEY" not in output


def test_missing_volume_is_not_silently_created(tmp_path, monkeypatch):
    # 卷未挂载时应报告故障，不能自动创建目录掩盖部署问题。
    missing = tmp_path / "missing-volume"
    monkeypatch.setattr(health, "get_settings", lambda: Settings(uploads_dir=missing))
    with pytest.raises(FileNotFoundError):
        health.check_storage()
    assert not missing.exists()


def test_storage_probe_cleans_up(tmp_path, monkeypatch):
    # 存储探针验证可写性后应删除临时文件。
    monkeypatch.setattr(health, "get_settings", lambda: Settings(uploads_dir=tmp_path))
    health.check_storage()
    assert list(tmp_path.iterdir()) == []


def test_error_envelope_uses_server_generated_request_id(client):
    # 客户端传入的请求 ID 不可信，响应和日志关联 ID 必须由服务端生成。
    response = client.get("/not-found", headers={"X-Request-ID": "untrusted-client-value"})
    body = response.json()
    assert response.status_code == 404
    assert body["code"] == "BIZ_404"
    assert len(body["request_id"]) == 32
    assert body["request_id"] == response.headers["x-request-id"]
    assert body["details"] == {}


def test_unhandled_failure_returns_safe_error(client, monkeypatch, capsys):
    def unexpected_failure():
        raise RuntimeError("PRIVATE_PASSWORD")

    monkeypatch.setattr(health_routes, "readiness", unexpected_failure)
    response = client.get("/health/ready")
    assert response.status_code == 500
    assert response.json()["code"] == "SYS_500"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "PRIVATE_PASSWORD" not in response.text + capsys.readouterr().err


def test_settings_repr_hides_password():
    settings = Settings(mysql_password="PRIVATE_PASSWORD")
    assert "PRIVATE_PASSWORD" not in repr(settings)
    assert "PRIVATE_PASSWORD" not in str(settings.database_url)


def test_log_formatter_does_not_serialize_arbitrary_fields():
    record = logging.LogRecord("test", logging.INFO, "", 0, "http_request", (), None)
    record.authorization = "PRIVATE_TOKEN"
    record.request_id = "example-id"
    encoded = JsonFormatter().format(record)
    assert "PRIVATE_TOKEN" not in encoded
    assert json.loads(encoded)["request_id"] == "example-id"
