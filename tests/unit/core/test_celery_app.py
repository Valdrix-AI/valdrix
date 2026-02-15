from app.shared.core.celery_app import celery_app


def test_celery_config():
    """Test Celery configuration settings."""
    conf = celery_app.conf

    # Assert critical production settings
    assert conf.task_serializer == "json"
    assert conf.accept_content == ["json"]
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True

    # Assert test mode settings (since we run in test env)
    # The app code has `if settings.TESTING: ...`
    # and settings.TESTING is likely True in this pytest run
    from app.shared.core.config import get_settings

    if get_settings().TESTING:
        assert conf.task_always_eager is True
