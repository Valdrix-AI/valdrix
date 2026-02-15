from app.shared.core import security_metrics as sm


def test_security_metrics_labelnames():
    assert sm.CSRF_ERRORS._labelnames == ("path", "method")
    assert sm.RATE_LIMIT_EXCEEDED._labelnames == ("path", "method", "tier")
    assert sm.REMEDIATION_TOTAL._labelnames == ("status", "resource_type", "action")
    assert sm.AUTH_FAILURES._labelnames == ("reason",)


def test_security_metrics_can_increment():
    sm.CSRF_ERRORS.labels(path="/", method="GET").inc()
    sm.RATE_LIMIT_EXCEEDED.labels(path="/", method="GET", tier="starter").inc()
    sm.REMEDIATION_TOTAL.labels(
        status="success", resource_type="ec2", action="stop"
    ).inc()
    sm.AUTH_FAILURES.labels(reason="invalid_token").inc()
