from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import dns.asyncresolver
import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_candidate import DiscoveryCandidate
from app.models.license_connection import LicenseConnection
from app.shared.core.http import get_http_client

logger = structlog.get_logger()

_MICROSOFT_LICENSE_VENDORS = {
    "microsoft_365",
    "microsoft365",
    "m365",
    "microsoft",
}
_GOOGLE_LICENSE_VENDORS = {
    "google_workspace",
    "googleworkspace",
    "gsuite",
    "google",
}

_DISCOVERY_STATUS_VALUES = {"pending", "accepted", "ignored", "connected"}


class DiscoveryWizardService:
    """
    Discovery wizard orchestration.

    Stage A:
    - Domain signals (MX, TXT, selected CNAME probes) to produce probable candidates.

    Stage B:
    - Best-effort IdP deep scan using an active License connector token
      (Microsoft Graph service principals; Google Workspace token sampling).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def discover_stage_a(
        self, tenant_id: UUID, email: str
    ) -> tuple[str, list[DiscoveryCandidate], list[str]]:
        domain = self._normalize_email_domain(email)
        signals, warnings = await self._collect_domain_signals(domain)
        drafts = self._build_stage_a_candidates(domain, signals)
        candidates = await self._upsert_candidates(tenant_id, domain, drafts)
        return domain, candidates, warnings

    async def deep_scan_idp(
        self,
        tenant_id: UUID,
        domain: str,
        idp_provider: str,
        *,
        max_users: int = 20,
    ) -> tuple[str, list[DiscoveryCandidate], list[str]]:
        normalized_domain = self._normalize_domain(domain)
        provider = idp_provider.strip().lower()
        if provider not in {"microsoft_365", "google_workspace"}:
            raise ValueError("idp_provider must be microsoft_365 or google_workspace")

        connection = await self._find_idp_license_connection(tenant_id, provider)
        if connection is None:
            raise ValueError(
                f"No active {provider} license connector found. "
                "Connect and verify License connector first, then run deep scan."
            )

        token = (connection.api_key or "").strip()
        if not token:
            raise ValueError(
                f"{provider} license connector is missing api_key token for deep scan."
            )

        warnings: list[str] = []
        if provider == "microsoft_365":
            app_names, provider_warnings = await self._scan_microsoft_enterprise_apps(
                token
            )
            warnings.extend(provider_warnings)
        else:
            app_names, provider_warnings = await self._scan_google_workspace_apps(
                token, max_users=max_users
            )
            warnings.extend(provider_warnings)

        drafts: list[dict[str, Any]] = [
            {
                "category": "license",
                "provider": provider,
                "source": "idp_deep_scan",
                "confidence_score": 0.99,
                "requires_admin_auth": True,
                "connection_target": "license",
                "connection_vendor_hint": provider,
                "evidence": [f"idp_deep_scan:{provider}"],
                "details": {
                    "idp_provider": provider,
                    "detected_apps": len(app_names),
                },
            }
        ]

        # Strong default cloud inference from primary identity provider.
        if provider == "microsoft_365":
            drafts.append(
                {
                    "category": "cloud_provider",
                    "provider": "azure",
                    "source": "idp_deep_scan",
                    "confidence_score": 0.82,
                    "requires_admin_auth": True,
                    "connection_target": "azure",
                    "connection_vendor_hint": None,
                    "evidence": ["idp_deep_scan:microsoft_365"],
                    "details": {"inference": "entra_primary_idp"},
                }
            )
        else:
            drafts.append(
                {
                    "category": "cloud_provider",
                    "provider": "gcp",
                    "source": "idp_deep_scan",
                    "confidence_score": 0.82,
                    "requires_admin_auth": True,
                    "connection_target": "gcp",
                    "connection_vendor_hint": None,
                    "evidence": ["idp_deep_scan:google_workspace"],
                    "details": {"inference": "google_workspace_primary_idp"},
                }
            )

        drafts.extend(self._build_app_name_candidates(app_names))
        candidates = await self._upsert_candidates(tenant_id, normalized_domain, drafts)
        return normalized_domain, candidates, warnings

    async def list_candidates(
        self, tenant_id: UUID, *, status: str | None = None
    ) -> list[DiscoveryCandidate]:
        stmt = select(DiscoveryCandidate).where(DiscoveryCandidate.tenant_id == tenant_id)
        if status:
            normalized_status = status.strip().lower()
            if normalized_status not in _DISCOVERY_STATUS_VALUES:
                raise ValueError(
                    f"Invalid status '{status}'. Expected one of: "
                    f"{', '.join(sorted(_DISCOVERY_STATUS_VALUES))}."
                )
            stmt = stmt.where(DiscoveryCandidate.status == normalized_status)
        stmt = stmt.order_by(
            DiscoveryCandidate.confidence_score.desc(),
            DiscoveryCandidate.provider.asc(),
            DiscoveryCandidate.created_at.desc(),
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_candidate_status(
        self, tenant_id: UUID, candidate_id: UUID, status: str
    ) -> DiscoveryCandidate:
        normalized_status = status.strip().lower()
        if normalized_status not in _DISCOVERY_STATUS_VALUES:
            raise ValueError(
                f"Invalid status '{status}'. Expected one of: "
                f"{', '.join(sorted(_DISCOVERY_STATUS_VALUES))}."
            )

        result = await self.db.execute(
            select(DiscoveryCandidate).where(
                DiscoveryCandidate.id == candidate_id,
                DiscoveryCandidate.tenant_id == tenant_id,
            )
        )
        candidate = result.scalar_one_or_none()
        if candidate is None:
            raise LookupError("Discovery candidate not found")

        candidate.status = normalized_status
        candidate.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(candidate)
        return candidate

    async def _upsert_candidates(
        self,
        tenant_id: UUID,
        domain: str,
        drafts: list[dict[str, Any]],
    ) -> list[DiscoveryCandidate]:
        now = datetime.now(timezone.utc)
        merged = self._merge_drafts(drafts)
        for draft in merged:
            existing_result = await self.db.execute(
                select(DiscoveryCandidate).where(
                    DiscoveryCandidate.tenant_id == tenant_id,
                    DiscoveryCandidate.domain == domain,
                    DiscoveryCandidate.category == draft["category"],
                    DiscoveryCandidate.provider == draft["provider"],
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing is None:
                self.db.add(
                    DiscoveryCandidate(
                        tenant_id=tenant_id,
                        domain=domain,
                        category=draft["category"],
                        parameters=dict(draft.get("parameters") or {}),
                        source=draft["source"],
                        status="pending",
                        confidence_score=float(draft["confidence_score"]),
                        requires_admin_auth=bool(draft["requires_admin_auth"]),
                        connection_target=draft.get("connection_target"),
                        connection_vendor_hint=draft.get("connection_vendor_hint"),
                        evidence=list(draft["evidence"]),
                        details=dict(draft["details"]),
                        last_seen_at=now,
                    )
                )
                continue

            existing.last_seen_at = now
            existing.requires_admin_auth = bool(draft["requires_admin_auth"])
            existing.connection_target = draft.get("connection_target")
            existing.connection_vendor_hint = draft.get("connection_vendor_hint")
            existing.evidence = list(draft["evidence"])
            existing.details = dict(draft["details"])

            incoming_confidence = float(draft["confidence_score"])
            # Do not silently downgrade confidence or source quality.
            if (
                incoming_confidence > float(existing.confidence_score)
                or draft["source"] == "idp_deep_scan"
            ):
                existing.confidence_score = incoming_confidence
                existing.source = draft["source"]

        await self.db.commit()
        result = await self.db.execute(
            select(DiscoveryCandidate)
            .where(
                DiscoveryCandidate.tenant_id == tenant_id,
                DiscoveryCandidate.domain == domain,
            )
            .order_by(
                DiscoveryCandidate.confidence_score.desc(),
                DiscoveryCandidate.provider.asc(),
            )
        )
        return list(result.scalars().all())

    async def _find_idp_license_connection(
        self, tenant_id: UUID, idp_provider: str
    ) -> LicenseConnection | None:
        aliases = (
            _MICROSOFT_LICENSE_VENDORS
            if idp_provider == "microsoft_365"
            else _GOOGLE_LICENSE_VENDORS
        )
        result = await self.db.execute(
            select(LicenseConnection)
            .where(
                LicenseConnection.tenant_id == tenant_id,
                LicenseConnection.vendor.in_(aliases),
                LicenseConnection.auth_method.in_(("api_key", "oauth")),
                LicenseConnection.api_key.is_not(None),
                LicenseConnection.is_active.is_(True),
            )
            .order_by(LicenseConnection.last_synced_at.desc())
        )
        return result.scalars().first()

    async def _collect_domain_signals(
        self, domain: str
    ) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        resolver = dns.asyncresolver.Resolver(configure=True)
        resolver.timeout = 2.0
        resolver.lifetime = 4.0

        mx_hosts = await self._resolve_dns_records(resolver, domain, "MX", warnings)
        txt_records = await self._resolve_dns_records(resolver, domain, "TXT", warnings)

        cname_targets: dict[str, str] = {}
        for prefix in (
            "autodiscover",
            "enterpriseenrollment",
            "enterpriseregistration",
            "slack",
            "stripe",
            "zoom",
            "datadog",
            "newrelic",
            "chat",
            "www",
            "mail",
        ):
            host = f"{prefix}.{domain}"
            values = await self._resolve_dns_records(resolver, host, "CNAME", warnings)
            if values:
                cname_targets[host] = values[0]

        return {
            "mx_hosts": mx_hosts,
            "txt_records": txt_records,
            "cname_targets": cname_targets,
        }, warnings

    async def _resolve_dns_records(
        self,
        resolver: dns.asyncresolver.Resolver,
        name: str,
        record_type: str,
        warnings: list[str],
    ) -> list[str]:
        try:
            answer = await resolver.resolve(name, record_type, raise_on_no_answer=False)
            if answer is None:
                return []
        except Exception as exc:  # noqa: BLE001 - best-effort discovery
            warnings.append(f"{record_type} lookup failed for {name}: {exc}")
            return []

        values: list[str] = []
        for record in answer:
            try:
                if record_type == "MX":
                    host = str(record.exchange).strip().rstrip(".").lower()
                    values.append(host)
                elif record_type == "CNAME":
                    target = str(record.target).strip().rstrip(".").lower()
                    values.append(target)
                elif record_type == "TXT":
                    text = record.to_text().strip().strip('"').lower()
                    values.append(text)
                else:
                    values.append(str(record).strip().lower())
            except Exception:  # noqa: BLE001 - ignore malformed record only
                continue
        return values

    def _build_stage_a_candidates(
        self, domain: str, signals: dict[str, Any]
    ) -> list[dict[str, Any]]:
        mx_hosts = [str(v).lower() for v in signals.get("mx_hosts", [])]
        txt_records = [str(v).lower() for v in signals.get("txt_records", [])]
        cname_targets = {
            str(k).lower(): str(v).lower()
            for k, v in (signals.get("cname_targets") or {}).items()
        }
        cname_values = list(cname_targets.values())

        drafts: list[dict[str, Any]] = []

        has_google_mx = any(
            ("google.com" in host) or ("googlemail.com" in host) for host in mx_hosts
        )
        has_google_spf = any("include:_spf.google.com" in txt for txt in txt_records)
        if has_google_mx or has_google_spf:
            evidence = []
            if has_google_mx:
                evidence.append("mx:google")
            if has_google_spf:
                evidence.append("spf:google")
            confidence = 0.93 if (has_google_mx and has_google_spf) else 0.82
            drafts.extend(
                [
                    {
                        "category": "license",
                        "provider": "google_workspace",
                        "source": "domain_dns",
                        "confidence_score": confidence,
                        "requires_admin_auth": True,
                        "connection_target": "license",
                        "connection_vendor_hint": "google_workspace",
                        "evidence": evidence,
                        "details": {"domain": domain},
                    },
                    {
                        "category": "cloud_provider",
                        "provider": "gcp",
                        "source": "domain_dns",
                        "confidence_score": 0.62,
                        "requires_admin_auth": True,
                        "connection_target": "gcp",
                        "connection_vendor_hint": None,
                        "evidence": evidence,
                        "details": {"inference": "google_workspace_domain_signals"},
                    },
                ]
            )

        has_ms_mx = any("protection.outlook.com" in host for host in mx_hosts)
        has_ms_spf = any(
            "include:spf.protection.outlook.com" in txt for txt in txt_records
        )
        has_ms_autodiscover = any("outlook.com" in v for v in cname_values)
        if has_ms_mx or has_ms_spf or has_ms_autodiscover:
            evidence = []
            if has_ms_mx:
                evidence.append("mx:microsoft")
            if has_ms_spf:
                evidence.append("spf:microsoft")
            if has_ms_autodiscover:
                evidence.append("cname:autodiscover")
            confidence = 0.93 if (has_ms_mx and has_ms_spf) else 0.82
            drafts.extend(
                [
                    {
                        "category": "license",
                        "provider": "microsoft_365",
                        "source": "domain_dns",
                        "confidence_score": confidence,
                        "requires_admin_auth": True,
                        "connection_target": "license",
                        "connection_vendor_hint": "microsoft_365",
                        "evidence": evidence,
                        "details": {"domain": domain},
                    },
                    {
                        "category": "cloud_provider",
                        "provider": "azure",
                        "source": "domain_dns",
                        "confidence_score": 0.62,
                        "requires_admin_auth": True,
                        "connection_target": "azure",
                        "connection_vendor_hint": None,
                        "evidence": evidence,
                        "details": {"inference": "microsoft_365_domain_signals"},
                    },
                ]
            )

        has_slack_signal = any("slack" in val for val in cname_values) or any(
            "slack-domain-verification" in txt for txt in txt_records
        )
        if has_slack_signal:
            drafts.append(
                {
                    "category": "cloud_plus",
                    "provider": "slack",
                    "source": "domain_dns",
                    "confidence_score": 0.72,
                    "requires_admin_auth": True,
                    "connection_target": "saas",
                    "connection_vendor_hint": "slack",
                    "evidence": ["cname_or_txt:slack"],
                    "details": {"domain": domain},
                }
            )

        has_stripe_signal = any("stripe" in val for val in cname_values) or any(
            "stripe-verification" in txt for txt in txt_records
        )
        if has_stripe_signal:
            drafts.append(
                {
                    "category": "cloud_plus",
                    "provider": "stripe",
                    "source": "domain_dns",
                    "confidence_score": 0.68,
                    "requires_admin_auth": True,
                    "connection_target": "saas",
                    "connection_vendor_hint": "stripe",
                    "evidence": ["cname_or_txt:stripe"],
                    "details": {"domain": domain},
                }
            )

        has_salesforce_signal = any(
            ("salesforce.com" in val) or ("force.com" in val) for val in cname_values
        )
        if has_salesforce_signal:
            drafts.append(
                {
                    "category": "cloud_plus",
                    "provider": "salesforce",
                    "source": "domain_dns",
                    "confidence_score": 0.68,
                    "requires_admin_auth": True,
                    "connection_target": "saas",
                    "connection_vendor_hint": "salesforce",
                    "evidence": ["cname:salesforce_or_force"],
                    "details": {"domain": domain},
                }
            )

        has_zoom_signal = any(
            ("zoom.us" in val) or ("zoom.com" in val) for val in cname_values
        ) or any(
            ("zoom-verification" in txt) or ("zoomsiteverify" in txt)
            for txt in txt_records
        )
        if has_zoom_signal:
            drafts.append(
                {
                    "category": "cloud_plus",
                    "provider": "zoom",
                    "source": "domain_dns",
                    "confidence_score": 0.64,
                    "requires_admin_auth": True,
                    "connection_target": "saas",
                    "connection_vendor_hint": "zoom",
                    "evidence": ["cname_or_txt:zoom"],
                    "details": {"domain": domain},
                }
            )

        has_datadog_signal = any(
            ("datadoghq.com" in val) or ("ddog-gov.com" in val) for val in cname_values
        ) or any("datadog" in txt for txt in txt_records)
        if has_datadog_signal:
            drafts.append(
                {
                    "category": "platform",
                    "provider": "datadog",
                    "source": "domain_dns",
                    "confidence_score": 0.66,
                    "requires_admin_auth": True,
                    "connection_target": "platform",
                    "connection_vendor_hint": "datadog",
                    "evidence": ["cname_or_txt:datadog"],
                    "details": {"domain": domain},
                }
            )

        has_newrelic_signal = any("newrelic" in val for val in cname_values) or any(
            "newrelic" in txt for txt in txt_records
        )
        if has_newrelic_signal:
            drafts.append(
                {
                    "category": "platform",
                    "provider": "newrelic",
                    "source": "domain_dns",
                    "confidence_score": 0.66,
                    "requires_admin_auth": True,
                    "connection_target": "platform",
                    "connection_vendor_hint": "newrelic",
                    "evidence": ["cname_or_txt:newrelic"],
                    "details": {"domain": domain},
                }
            )

        has_github_signal = any(
            ("github.io" in val)
            or ("githubusercontent.com" in val)
            or ("github.com" in val)
            for val in cname_values
        )
        if has_github_signal:
            drafts.append(
                {
                    "category": "cloud_plus",
                    "provider": "github",
                    "source": "domain_dns",
                    "confidence_score": 0.60,
                    "requires_admin_auth": True,
                    "connection_target": "saas",
                    "connection_vendor_hint": "github",
                    "evidence": ["cname:github_pages"],
                    "details": {"domain": domain},
                }
            )

        has_aws_signal = any(
            ("amazonses.com" in txt) or ("amazonaws.com" in txt)
            for txt in txt_records
        )
        if has_aws_signal:
            drafts.append(
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
                }
            )

        return drafts

    def _build_app_name_candidates(self, app_names: list[str]) -> list[dict[str, Any]]:
        drafts: list[dict[str, Any]] = []
        mappings = [
            (
                "cloud_provider",
                "aws",
                "aws",
                None,
                (
                    "amazon web services",
                    "aws",
                    "iam identity center",
                    "aws single sign-on",
                ),
                0.9,
            ),
            (
                "cloud_provider",
                "azure",
                "azure",
                None,
                ("azure", "microsoft azure"),
                0.84,
            ),
            (
                "cloud_provider",
                "gcp",
                "gcp",
                None,
                ("google cloud", "gcp", "bigquery", "cloud run"),
                0.86,
            ),
            (
                "cloud_plus",
                "stripe",
                "saas",
                "stripe",
                ("stripe",),
                0.86,
            ),
            (
                "cloud_plus",
                "slack",
                "saas",
                "slack",
                ("slack",),
                0.86,
            ),
            (
                "cloud_plus",
                "github",
                "saas",
                "github",
                ("github",),
                0.86,
            ),
            (
                "cloud_plus",
                "zoom",
                "saas",
                "zoom",
                ("zoom",),
                0.84,
            ),
            (
                "cloud_plus",
                "salesforce",
                "saas",
                "salesforce",
                ("salesforce", "sfdc"),
                0.88,
            ),
            (
                "platform",
                "datadog",
                "platform",
                "datadog",
                ("datadog",),
                0.84,
            ),
            (
                "platform",
                "newrelic",
                "platform",
                "newrelic",
                ("new relic", "newrelic"),
                0.84,
            ),
        ]

        for raw_name in app_names:
            name = raw_name.strip()
            if not name:
                continue
            lowered = name.lower()
            for category, provider, target, vendor_hint, keywords, confidence in mappings:
                if any(keyword in lowered for keyword in keywords):
                    drafts.append(
                        {
                            "category": category,
                            "provider": provider,
                            "source": "idp_deep_scan",
                            "confidence_score": confidence,
                            "requires_admin_auth": True,
                            "connection_target": target,
                            "connection_vendor_hint": vendor_hint,
                            "evidence": [f"idp_app:{name}"],
                            "details": {"matched_app_name": name},
                        }
                    )
        return drafts

    async def _scan_microsoft_enterprise_apps(
        self, token: str
    ) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        headers = {"Authorization": f"Bearer {token}"}
        url = (
            "https://graph.microsoft.com/v1.0/servicePrincipals"
            "?$select=displayName,appId,servicePrincipalType&$top=999"
        )
        discovered_names: list[str] = []
        page_count = 0
        while url and page_count < 5:
            page_count += 1
            try:
                payload = await self._request_json("GET", url, headers=headers)
            except ValueError as exc:
                warnings.append(f"microsoft_graph_scan_failed: {exc}")
                break

            entries = payload.get("value", [])
            if isinstance(entries, list):
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    display_name = str(entry.get("displayName") or "").strip()
                    if display_name:
                        discovered_names.append(display_name)

            next_link = payload.get("@odata.nextLink")
            url = str(next_link).strip() if isinstance(next_link, str) else ""

        return sorted(set(discovered_names)), warnings

    async def _scan_google_workspace_apps(
        self, token: str, *, max_users: int
    ) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        headers = {"Authorization": f"Bearer {token}"}
        users_url = (
            "https://admin.googleapis.com/admin/directory/v1/users"
            "?customer=my_customer&maxResults=100&projection=basic"
        )
        try:
            users_payload = await self._request_json("GET", users_url, headers=headers)
        except ValueError as exc:
            warnings.append(f"google_workspace_user_scan_failed: {exc}")
            return [], warnings

        users = users_payload.get("users", [])
        if not isinstance(users, list):
            users = []

        discovered_names: set[str] = set()
        sampled = 0
        permission_errors = 0
        for user in users:
            if sampled >= max_users:
                break
            if not isinstance(user, dict):
                continue
            email = str(user.get("primaryEmail") or "").strip()
            if not email:
                continue
            sampled += 1
            token_url = (
                "https://admin.googleapis.com/admin/directory/v1/users/"
                f"{email}/tokens"
            )
            try:
                token_payload = await self._request_json(
                    "GET", token_url, headers=headers, allow_404=True
                )
            except ValueError as exc:
                message = str(exc)
                warnings.append(f"google_workspace_token_scan_failed:{email}:{message}")
                if "status 403" in message:
                    permission_errors += 1
                if permission_errors >= 3:
                    warnings.append(
                        "google_workspace_token_scan_aborted: repeated 403 responses"
                    )
                    break
                continue

            items = token_payload.get("items", [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = str(
                    item.get("displayText") or item.get("clientId") or ""
                ).strip()
                if label:
                    discovered_names.add(label)

        return sorted(discovered_names), warnings

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        allow_404: bool = False,
    ) -> dict[str, Any]:
        client = get_http_client()
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = await client.request(method, url, headers=headers)
                if allow_404 and response.status_code == 404:
                    return {}
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                    continue
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    return payload
                if isinstance(payload, list):
                    return {"value": payload}
                raise ValueError("invalid_payload_shape")
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == 3:
                    break
        raise ValueError(f"request_failed:{url}: {last_error}")

    def _merge_drafts(self, drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for draft in drafts:
            key = (str(draft["category"]), str(draft["provider"]))
            existing = merged.get(key)
            if existing is None:
                merged[key] = {
                    **draft,
                    "evidence": list(dict.fromkeys(draft.get("evidence", []))),
                }
                continue

            if float(draft.get("confidence_score", 0.0)) > float(
                existing.get("confidence_score", 0.0)
            ):
                existing["confidence_score"] = float(draft["confidence_score"])
                existing["source"] = str(draft.get("source", existing.get("source")))
                existing["details"] = dict(draft.get("details") or existing.get("details") or {})
                existing["connection_target"] = draft.get(
                    "connection_target", existing.get("connection_target")
                )
                existing["connection_vendor_hint"] = draft.get(
                    "connection_vendor_hint", existing.get("connection_vendor_hint")
                )
                existing["requires_admin_auth"] = bool(
                    draft.get("requires_admin_auth", existing.get("requires_admin_auth"))
                )

            existing_evidence = list(existing.get("evidence", []))
            for signal in draft.get("evidence", []):
                if signal not in existing_evidence:
                    existing_evidence.append(signal)
            existing["evidence"] = existing_evidence

        return list(merged.values())

    def _normalize_email_domain(self, email: str) -> str:
        value = str(email or "").strip().lower()
        if "@" not in value:
            raise ValueError("email must contain a valid domain")
        return self._normalize_domain(value.split("@", 1)[1])

    def _normalize_domain(self, domain: str) -> str:
        normalized = str(domain or "").strip().lower().strip(".")
        if "." not in normalized:
            raise ValueError("domain must be fully qualified, e.g. example.com")
        return normalized
