import builtins
import importlib.util

import pytest


def test_billing_domain_init_exports() -> None:
    """
    app.modules.billing.domain.billing.__init__ guards its imports.
    In our test environment, the happy-path imports should succeed.
    """
    from app.modules.billing.domain import billing as billing_domain

    # If the guarded imports succeed, __all__ should be populated.
    assert billing_domain.__all__


def test_billing_domain_init_import_error_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The module should fail fast when required billing implementation imports fail.
    """
    import app.modules.billing.domain.billing as billing_domain

    module_path = getattr(billing_domain, "__file__", None)
    assert isinstance(module_path, str) and module_path

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "app.modules.billing.domain.billing.paystack_billing":
            raise ImportError("forced for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    spec = importlib.util.spec_from_file_location(
        "tests._billing_domain_init_import_error",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    with pytest.raises(ImportError, match="forced for test"):
        spec.loader.exec_module(module)
