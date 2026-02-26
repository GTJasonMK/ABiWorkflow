from __future__ import annotations

from app.services import progress


def test_publish_progress_should_not_raise_when_redis_unavailable(monkeypatch):
    progress._redis_client = None  # type: ignore[attr-defined]
    progress._redis_unavailable = False  # type: ignore[attr-defined]

    def fake_from_url(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.services.progress.redis.from_url", fake_from_url)

    # Redis 不可用时不应影响主链路。
    progress.publish_progress("project-1", "generate_progress", {"percent": 10})

    assert progress._redis_unavailable is True  # type: ignore[attr-defined]


def test_publish_progress_should_not_raise_when_publish_failed(monkeypatch):
    class FakeRedisClient:
        def publish(self, channel: str, payload: str) -> None:
            raise RuntimeError("publish failed")

    monkeypatch.setattr("app.services.progress.get_redis_sync", lambda: FakeRedisClient())

    # publish 异常也应被吞掉，保证业务流程继续。
    progress.publish_progress("project-2", "compose_progress", {"percent": 70})

