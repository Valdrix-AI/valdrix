from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.shared.connections.discovery import DiscoveryWizardService


class _FakeScalars:
    def __init__(self, values: list[object]):
        self._values = list(values)

    def all(self) -> list[object]:
        return list(self._values)

    def first(self) -> object | None:
        return self._values[0] if self._values else None


class _FakeResult:
    def __init__(self, *, one: object | None = None, values: list[object] | None = None):
        self._one = one
        self._values = list(values or [])

    def scalar_one_or_none(self) -> object | None:
        return self._one

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._values)


class _FakeDB:
    def __init__(self, results: list[_FakeResult]):
        self._results = list(results)
        self.added: list[object] = []
        self.commits = 0
        self.refreshed: list[object] = []

    async def execute(self, _stmt: object) -> _FakeResult:
        if not self._results:
            raise AssertionError("No fake DB result configured for execute")
        return self._results.pop(0)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, item: object) -> None:
        self.refreshed.append(item)


class _FakeHttpClient:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def request(self, method: str, url: str, headers: dict[str, str]) -> httpx.Response:
        self.calls.append((method, url))
        if not self.responses:
            raise AssertionError("No fake response configured for HTTP request")
        next_item = self.responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


def _json_response(status_code: int, payload: object) -> httpx.Response:
    request = httpx.Request("GET", "https://example.invalid")
    return httpx.Response(status_code, request=request, json=payload)


class _MXRecord:
    def __init__(self, exchange: str):
        self.exchange = exchange


class _BrokenMXRecord:
    @property
    def exchange(self) -> str:
        raise RuntimeError("bad record")


class _CNAMERecord:
    def __init__(self, target: str):
        self.target = target


class _TXTRecord:
    def __init__(self, text: str):
        self._text = text

    def to_text(self) -> str:
        return self._text


@pytest.mark.asyncio
async def test_discover_stage_a_orchestrates_calls() -> None:
    service = DiscoveryWizardService(MagicMock())
    tenant_id = uuid4()
    fake_signals = {"mx_hosts": [], "txt_records": [], "cname_targets": {}}
    fake_drafts = [{"provider": "aws"}]
    fake_candidates = [{"id": "candidate-1"}]

    with (
        patch.object(
            service,
            "_collect_domain_signals",
            new=AsyncMock(return_value=(fake_signals, ["dns_warning"])),
        ),
        patch.object(
            service,
            "_build_stage_a_candidates",
            return_value=fake_drafts,
        ) as build_mock,
        patch.object(
            service,
            "_upsert_candidates",
            new=AsyncMock(return_value=fake_candidates),
        ) as upsert_mock,
    ):
        domain, candidates, warnings = await service.discover_stage_a(
            tenant_id, "Owner@Example.COM"
        )

    assert domain == "example.com"
    assert candidates == fake_candidates
    assert warnings == ["dns_warning"]
    build_mock.assert_called_once_with("example.com", fake_signals)
    upsert_mock.assert_awaited_once_with(tenant_id, "example.com", fake_drafts)


@pytest.mark.asyncio
async def test_deep_scan_idp_microsoft_path_builds_default_cloud_inference() -> None:
    service = DiscoveryWizardService(MagicMock())
    tenant_id = uuid4()
    fake_connection = SimpleNamespace(api_key=" m365-token ")
    app_drafts = [
        {
            "category": "cloud_plus",
            "provider": "slack",
            "source": "idp_deep_scan",
            "confidence_score": 0.86,
            "requires_admin_auth": True,
            "connection_target": "saas",
            "connection_vendor_hint": "slack",
            "evidence": ["idp_app:Slack"],
            "details": {"matched_app_name": "Slack"},
        }
    ]

    with (
        patch.object(
            service,
            "_find_idp_license_connection",
            new=AsyncMock(return_value=fake_connection),
        ),
        patch.object(
            service,
            "_scan_microsoft_enterprise_apps",
            new=AsyncMock(return_value=(["Slack"], ["ms_warning"])),
        ),
        patch.object(service, "_build_app_name_candidates", return_value=app_drafts),
        patch.object(
            service,
            "_upsert_candidates",
            new=AsyncMock(return_value=[{"id": "stored"}]),
        ) as upsert_mock,
    ):
        domain, candidates, warnings = await service.deep_scan_idp(
            tenant_id, "Example.COM.", "microsoft_365"
        )

    assert domain == "example.com"
    assert candidates == [{"id": "stored"}]
    assert warnings == ["ms_warning"]

    drafts = upsert_mock.await_args.args[2]
    providers = {(item["category"], item["provider"]) for item in drafts}
    assert ("license", "microsoft_365") in providers
    assert ("cloud_provider", "azure") in providers
    assert ("cloud_plus", "slack") in providers


@pytest.mark.asyncio
async def test_deep_scan_idp_google_path_uses_max_users() -> None:
    service = DiscoveryWizardService(MagicMock())
    tenant_id = uuid4()
    fake_connection = SimpleNamespace(api_key="google-token")

    with (
        patch.object(
            service,
            "_find_idp_license_connection",
            new=AsyncMock(return_value=fake_connection),
        ),
        patch.object(
            service,
            "_scan_google_workspace_apps",
            new=AsyncMock(return_value=(["GitHub"], ["gw_warning"])),
        ) as scan_mock,
        patch.object(service, "_build_app_name_candidates", return_value=[]),
        patch.object(service, "_upsert_candidates", new=AsyncMock(return_value=[])),
    ):
        domain, candidates, warnings = await service.deep_scan_idp(
            tenant_id, "corp.example.com", "google_workspace", max_users=7
        )

    assert domain == "corp.example.com"
    assert candidates == []
    assert warnings == ["gw_warning"]
    scan_mock.assert_awaited_once_with("google-token", max_users=7)


@pytest.mark.asyncio
async def test_deep_scan_idp_validation_errors() -> None:
    service = DiscoveryWizardService(MagicMock())
    tenant_id = uuid4()

    with pytest.raises(ValueError, match="idp_provider must be"):
        await service.deep_scan_idp(tenant_id, "example.com", "okta")

    with patch.object(
        service, "_find_idp_license_connection", new=AsyncMock(return_value=None)
    ):
        with pytest.raises(ValueError, match="No active google_workspace"):
            await service.deep_scan_idp(tenant_id, "example.com", "google_workspace")

    with patch.object(
        service,
        "_find_idp_license_connection",
        new=AsyncMock(return_value=SimpleNamespace(api_key="   ")),
    ):
        with pytest.raises(ValueError, match="missing api_key token"):
            await service.deep_scan_idp(tenant_id, "example.com", "google_workspace")


@pytest.mark.asyncio
async def test_list_candidates_validates_status_and_returns_scalars() -> None:
    rows = [SimpleNamespace(provider="aws"), SimpleNamespace(provider="gcp")]
    db = _FakeDB([_FakeResult(values=rows), _FakeResult(values=rows)])
    service = DiscoveryWizardService(db)

    assert await service.list_candidates(uuid4()) == rows
    assert await service.list_candidates(uuid4(), status="IGNORED") == rows

    with pytest.raises(ValueError, match="Invalid status"):
        await service.list_candidates(uuid4(), status="bad-status")


@pytest.mark.asyncio
async def test_update_candidate_status_updates_existing_row() -> None:
    candidate = SimpleNamespace(status="pending", updated_at=None)
    db = _FakeDB([_FakeResult(one=candidate)])
    service = DiscoveryWizardService(db)

    updated = await service.update_candidate_status(uuid4(), uuid4(), "ACCEPTED")

    assert updated is candidate
    assert candidate.status == "accepted"
    assert isinstance(candidate.updated_at, datetime)
    assert candidate.updated_at.tzinfo is timezone.utc
    assert db.commits == 1
    assert db.refreshed == [candidate]


@pytest.mark.asyncio
async def test_update_candidate_status_errors_for_invalid_status_and_missing_candidate() -> None:
    service = DiscoveryWizardService(_FakeDB([]))
    with pytest.raises(ValueError, match="Invalid status"):
        await service.update_candidate_status(uuid4(), uuid4(), "nonsense")

    missing_db = _FakeDB([_FakeResult(one=None)])
    missing_service = DiscoveryWizardService(missing_db)
    with pytest.raises(LookupError, match="not found"):
        await missing_service.update_candidate_status(uuid4(), uuid4(), "ignored")


@pytest.mark.asyncio
async def test_upsert_candidates_creates_new_rows_and_updates_existing_rows() -> None:
    tenant_id = uuid4()
    existing = SimpleNamespace(
        confidence_score=0.30,
        source="domain_dns",
        requires_admin_auth=False,
        connection_target=None,
        connection_vendor_hint=None,
        evidence=[],
        details={"old": True},
        last_seen_at=None,
    )
    final_rows = [SimpleNamespace(id="final-1")]
    db = _FakeDB(
        [
            _FakeResult(one=existing),
            _FakeResult(one=None),
            _FakeResult(values=final_rows),
        ]
    )
    service = DiscoveryWizardService(db)

    drafts = [
        {
            "category": "cloud_provider",
            "provider": "azure",
            "source": "idp_deep_scan",
            "confidence_score": 0.91,
            "requires_admin_auth": True,
            "connection_target": "azure",
            "connection_vendor_hint": None,
            "evidence": ["idp_deep_scan:microsoft_365"],
            "details": {"new": True},
        },
        {
            "category": "cloud_provider",
            "provider": "aws",
            "source": "domain_dns",
            "confidence_score": 0.45,
            "requires_admin_auth": True,
            "connection_target": "aws",
            "connection_vendor_hint": None,
            "evidence": ["txt:amazonaws_or_amazonses"],
            "details": {"inference": "dns_txt_aws_signal"},
        },
    ]

    returned = await service._upsert_candidates(tenant_id, "example.com", drafts)

    assert returned == final_rows
    assert db.commits == 1
    assert len(db.added) == 1
    assert getattr(db.added[0], "provider") == "aws"
    assert existing.source == "idp_deep_scan"
    assert existing.confidence_score == pytest.approx(0.91)
    assert existing.connection_target == "azure"
    assert existing.details == {"new": True}
    assert existing.evidence == ["idp_deep_scan:microsoft_365"]
    assert isinstance(existing.last_seen_at, datetime)


@pytest.mark.asyncio
async def test_find_idp_license_connection_returns_first_result() -> None:
    connection = SimpleNamespace(vendor="microsoft_365")
    db = _FakeDB([_FakeResult(values=[connection]), _FakeResult(values=[connection])])
    service = DiscoveryWizardService(db)

    assert await service._find_idp_license_connection(uuid4(), "microsoft_365") is connection
    assert await service._find_idp_license_connection(uuid4(), "google_workspace") is connection


@pytest.mark.asyncio
async def test_collect_domain_signals_runs_all_dns_probes() -> None:
    service = DiscoveryWizardService(MagicMock())

    async def fake_resolve(
        _resolver: object, name: str, record_type: str, warnings: list[str]
    ) -> list[str]:
        assert warnings == []
        if record_type == "MX":
            return ["aspmx.l.google.com"]
        if record_type == "TXT":
            return ["v=spf1 include:_spf.google.com ~all"]
        if name.startswith("slack."):
            return ["acme.slack.com"]
        if name.startswith("mail."):
            return ["mx1.mailhost.com"]
        return []

    with (
        patch(
            "app.shared.connections.discovery.dns.asyncresolver.Resolver",
            return_value=MagicMock(),
        ),
        patch.object(
            service, "_resolve_dns_records", new=AsyncMock(side_effect=fake_resolve)
        ) as resolve_mock,
    ):
        signals, warnings = await service._collect_domain_signals("example.com")

    assert warnings == []
    assert signals["mx_hosts"] == ["aspmx.l.google.com"]
    assert signals["txt_records"] == ["v=spf1 include:_spf.google.com ~all"]
    assert signals["cname_targets"]["slack.example.com"] == "acme.slack.com"
    assert signals["cname_targets"]["mail.example.com"] == "mx1.mailhost.com"
    assert resolve_mock.await_count == 13


@pytest.mark.asyncio
async def test_resolve_dns_records_parses_supported_record_types_and_failures() -> None:
    service = DiscoveryWizardService(MagicMock())
    warnings: list[str] = []

    resolver = MagicMock()
    resolver.resolve = AsyncMock(return_value=[_MXRecord("ASPMX.L.GOOGLE.COM."), _BrokenMXRecord()])
    mx_values = await service._resolve_dns_records(resolver, "example.com", "MX", warnings)
    assert mx_values == ["aspmx.l.google.com"]

    resolver.resolve = AsyncMock(return_value=[_CNAMERecord("Acme.Slack.COM.")])
    cname_values = await service._resolve_dns_records(
        resolver, "slack.example.com", "CNAME", warnings
    )
    assert cname_values == ["acme.slack.com"]

    resolver.resolve = AsyncMock(return_value=[_TXTRecord('"ZoomSiteVerify=abc123"')])
    txt_values = await service._resolve_dns_records(resolver, "example.com", "TXT", warnings)
    assert txt_values == ["zoomsiteverify=abc123"]

    resolver.resolve = AsyncMock(return_value=["RAW-VALUE"])
    raw_values = await service._resolve_dns_records(resolver, "example.com", "SRV", warnings)
    assert raw_values == ["raw-value"]

    resolver.resolve = AsyncMock(return_value=None)
    assert await service._resolve_dns_records(resolver, "example.com", "TXT", warnings) == []

    resolver.resolve = AsyncMock(side_effect=RuntimeError("dns down"))
    assert await service._resolve_dns_records(resolver, "example.com", "TXT", warnings) == []
    assert any("TXT lookup failed for example.com" in message for message in warnings)


def test_build_stage_a_candidates_detects_multiple_signal_types() -> None:
    service = DiscoveryWizardService(MagicMock())
    signals = {
        "mx_hosts": ["aspmx.l.google.com", "example.mail.protection.outlook.com"],
        "txt_records": [
            "v=spf1 include:_spf.google.com include:spf.protection.outlook.com ~all",
            "slack-domain-verification=abc123",
            "stripe-verification=xyz789",
            "zoomsiteverify=zoom123",
            "newrelic-domain-verification=nr123",
            "amazonaws.com",
        ],
        "cname_targets": {
            "autodiscover.example.com": "autodiscover.outlook.com",
            "slack.example.com": "acme.slack.com",
            "stripe.example.com": "billing.stripe.com",
            "salesforce.example.com": "org.my.salesforce.com",
            "zoom.example.com": "acme.zoom.us",
            "datadog.example.com": "acme.datadoghq.com",
            "newrelic.example.com": "acme.newrelic.com",
            "github.example.com": "acme.github.io",
        },
    }

    drafts = service._build_stage_a_candidates("example.com", signals)
    providers = {draft["provider"] for draft in drafts}
    expected = {
        "google_workspace",
        "gcp",
        "microsoft_365",
        "azure",
        "slack",
        "stripe",
        "salesforce",
        "zoom",
        "datadog",
        "newrelic",
        "github",
        "aws",
    }
    assert expected.issubset(providers)

    google_draft = next(item for item in drafts if item["provider"] == "google_workspace")
    microsoft_draft = next(item for item in drafts if item["provider"] == "microsoft_365")
    assert google_draft["confidence_score"] == pytest.approx(0.93)
    assert microsoft_draft["confidence_score"] == pytest.approx(0.93)


def test_build_app_name_candidates_maps_known_keywords_and_ignores_blank_values() -> None:
    service = DiscoveryWizardService(MagicMock())
    app_names = [
        " Amazon Web Services ",
        "Microsoft Azure",
        "Google Cloud BigQuery",
        "Stripe Billing",
        "Slack",
        "GitHub Enterprise",
        "Zoom",
        "SFDC CPQ",
        "Datadog",
        "New Relic One",
        "   ",
    ]

    drafts = service._build_app_name_candidates(app_names)
    providers = {draft["provider"] for draft in drafts}
    assert {
        "aws",
        "azure",
        "gcp",
        "stripe",
        "slack",
        "github",
        "zoom",
        "salesforce",
        "datadog",
        "newrelic",
    }.issubset(providers)
    assert all(draft["source"] == "idp_deep_scan" for draft in drafts)


@pytest.mark.asyncio
async def test_scan_microsoft_enterprise_apps_paginates_and_handles_errors() -> None:
    service = DiscoveryWizardService(MagicMock())
    payload_one = {
        "value": [{"displayName": "Slack"}, {"displayName": "AWS"}, "bad-entry"],
        "@odata.nextLink": "https://graph.microsoft.com/next-page",
    }
    payload_two = {"value": [{"displayName": "Slack"}, {"displayName": "Datadog"}]}

    with patch.object(
        service,
        "_request_json",
        new=AsyncMock(side_effect=[payload_one, payload_two]),
    ):
        names, warnings = await service._scan_microsoft_enterprise_apps("token")

    assert warnings == []
    assert names == ["AWS", "Datadog", "Slack"]

    with patch.object(
        service,
        "_request_json",
        new=AsyncMock(side_effect=ValueError("graph unavailable")),
    ):
        names, warnings = await service._scan_microsoft_enterprise_apps("token")

    assert names == []
    assert warnings and warnings[0].startswith("microsoft_graph_scan_failed:")


@pytest.mark.asyncio
async def test_scan_google_workspace_apps_collects_items_and_limits_users() -> None:
    service = DiscoveryWizardService(MagicMock())
    users_payload = {
        "users": [
            {"primaryEmail": "a@example.com"},
            {"primaryEmail": "b@example.com"},
            {"primaryEmail": "c@example.com"},
            "not-a-user",
            {"primaryEmail": ""},
        ]
    }

    async def fake_request(
        _method: str,
        url: str,
        *,
        headers: dict[str, str],
        allow_404: bool = False,
    ) -> dict[str, object]:
        assert headers["Authorization"].startswith("Bearer ")
        if "users?customer=my_customer" in url:
            return users_payload
        if "/a@example.com/tokens" in url:
            assert allow_404 is True
            return {"items": [{"displayText": "Slack"}, {"clientId": "client-a"}]}
        if "/b@example.com/tokens" in url:
            return {"items": "bad-shape"}
        raise AssertionError(f"Unexpected token URL: {url}")

    with patch.object(service, "_request_json", new=AsyncMock(side_effect=fake_request)):
        names, warnings = await service._scan_google_workspace_apps("token", max_users=2)

    assert warnings == []
    assert set(names) == {"Slack", "client-a"}


@pytest.mark.asyncio
async def test_scan_google_workspace_apps_user_scan_failure_and_repeated_403_abort() -> None:
    service = DiscoveryWizardService(MagicMock())

    with patch.object(
        service,
        "_request_json",
        new=AsyncMock(side_effect=ValueError("directory error")),
    ):
        names, warnings = await service._scan_google_workspace_apps("token", max_users=5)

    assert names == []
    assert warnings and warnings[0].startswith("google_workspace_user_scan_failed:")

    state = {"token_calls": 0}

    async def fake_request(
        _method: str,
        url: str,
        *,
        headers: dict[str, str],
        allow_404: bool = False,
    ) -> dict[str, object]:
        assert headers["Authorization"].startswith("Bearer ")
        if "users?customer=my_customer" in url:
            return {
                "users": [
                    {"primaryEmail": "u1@example.com"},
                    {"primaryEmail": "u2@example.com"},
                    {"primaryEmail": "u3@example.com"},
                    {"primaryEmail": "u4@example.com"},
                ]
            }
        state["token_calls"] += 1
        assert allow_404 is True
        raise ValueError("status 403 forbidden")

    with patch.object(service, "_request_json", new=AsyncMock(side_effect=fake_request)):
        names, warnings = await service._scan_google_workspace_apps("token", max_users=20)

    assert names == []
    assert state["token_calls"] == 3
    assert any("google_workspace_token_scan_aborted" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_request_json_allows_404_retries_and_normalizes_list_payloads() -> None:
    service = DiscoveryWizardService(MagicMock())
    client = _FakeHttpClient(
        [
            _json_response(404, {"ignored": True}),
            _json_response(500, {"error": "retry"}),
            _json_response(200, [{"id": "a"}]),
        ]
    )

    with patch("app.shared.connections.discovery.get_http_client", return_value=client):
        assert (
            await service._request_json(
                "GET",
                "https://example.invalid/not-found",
                headers={"Authorization": "Bearer t"},
                allow_404=True,
            )
            == {}
        )
        payload = await service._request_json(
            "GET",
            "https://example.invalid/list",
            headers={"Authorization": "Bearer t"},
        )

    assert payload == {"value": [{"id": "a"}]}
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_request_json_raises_after_exhausted_errors() -> None:
    service = DiscoveryWizardService(MagicMock())

    invalid_payload_client = _FakeHttpClient(
        [
            _json_response(200, "bad"),
            _json_response(200, "bad"),
            _json_response(200, "bad"),
        ]
    )
    with patch(
        "app.shared.connections.discovery.get_http_client",
        return_value=invalid_payload_client,
    ):
        with pytest.raises(ValueError, match="request_failed:https://example.invalid/payload"):
            await service._request_json(
                "GET",
                "https://example.invalid/payload",
                headers={"Authorization": "Bearer t"},
            )

    transport_error_client = _FakeHttpClient(
        [
            httpx.ConnectError("c1"),
            httpx.ConnectError("c2"),
            httpx.ConnectError("c3"),
        ]
    )
    with patch(
        "app.shared.connections.discovery.get_http_client",
        return_value=transport_error_client,
    ):
        with pytest.raises(ValueError, match="request_failed:https://example.invalid/network"):
            await service._request_json(
                "GET",
                "https://example.invalid/network",
                headers={"Authorization": "Bearer t"},
            )


def test_merge_drafts_prefers_higher_confidence_and_merges_evidence() -> None:
    service = DiscoveryWizardService(MagicMock())
    drafts = [
        {
            "category": "cloud_provider",
            "provider": "azure",
            "source": "domain_dns",
            "confidence_score": 0.62,
            "requires_admin_auth": False,
            "connection_target": "azure",
            "connection_vendor_hint": None,
            "evidence": ["signal-a", "signal-a"],
            "details": {"from": "dns"},
        },
        {
            "category": "cloud_provider",
            "provider": "azure",
            "source": "idp_deep_scan",
            "confidence_score": 0.91,
            "requires_admin_auth": True,
            "connection_target": "azure",
            "connection_vendor_hint": "microsoft_365",
            "evidence": ["signal-b"],
            "details": {"from": "idp"},
        },
        {
            "category": "cloud_provider",
            "provider": "azure",
            "source": "domain_dns",
            "confidence_score": 0.30,
            "requires_admin_auth": True,
            "connection_target": "azure",
            "connection_vendor_hint": None,
            "evidence": ["signal-b", "signal-c"],
            "details": {"from": "low"},
        },
    ]

    merged = service._merge_drafts(drafts)
    assert len(merged) == 1
    item = merged[0]
    assert item["confidence_score"] == pytest.approx(0.91)
    assert item["source"] == "idp_deep_scan"
    assert item["requires_admin_auth"] is True
    assert item["connection_vendor_hint"] == "microsoft_365"
    assert item["details"] == {"from": "idp"}
    assert item["evidence"] == ["signal-a", "signal-b", "signal-c"]


def test_normalize_domain_helpers() -> None:
    service = DiscoveryWizardService(MagicMock())

    assert service._normalize_email_domain("Admin@Example.COM") == "example.com"
    assert service._normalize_domain("Example.com.") == "example.com"

    with pytest.raises(ValueError, match="email must contain a valid domain"):
        service._normalize_email_domain("not-an-email")

    with pytest.raises(ValueError, match="fully qualified"):
        service._normalize_domain("localhost")
