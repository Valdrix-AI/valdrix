import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.optimization.domain.service import ZombieService
from app.models.aws_connection import AWSConnection
from app.models.gcp_connection import GCPConnection


@pytest.fixture
def db_session():
    """Mock database session."""
    session = MagicMock(spec=AsyncSession)
    session.bind = MagicMock()
    session.bind.url = "sqlite://"
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.info = {}
    return session


@pytest.fixture
def zombie_service(db_session):
    return ZombieService(db_session)


@pytest.mark.asyncio
async def test_scan_for_tenant_no_connections(zombie_service, db_session):
    tenant_id = uuid4()
    user = MagicMock(tenant_id=tenant_id)

    # Mock all connection models returning empty lists
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    db_session.execute.return_value = mock_res

    results = await zombie_service.scan_for_tenant(tenant_id, user)

    assert results["total_monthly_waste"] == 0.0
    assert "No cloud connections found" in results["error"]


@pytest.mark.asyncio
async def test_scan_for_tenant_parallel_success(zombie_service, db_session):
    tenant_id = uuid4()
    user = MagicMock(tenant_id=tenant_id)

    # Mock AWS and GCP connections
    aws_conn = AWSConnection(id=uuid4(), tenant_id=tenant_id)
    gcp_conn = GCPConnection(id=uuid4(), tenant_id=tenant_id)

    # Mock DB query
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.side_effect = [[aws_conn], [], [gcp_conn]]
    db_session.execute.return_value = mock_res

    # Mock Detector Success
    mock_detector = MagicMock()
    mock_detector.scan_all = AsyncMock(
        return_value={
            "unattached_volumes": [{"id": "v-1", "monthly_waste": 10.0}],
            "idle_instances": [{"id": "i-1", "monthly_waste": 20.0}],
        }
    )
    mock_detector.get_credentials = AsyncMock(
        return_value={"AccessKeyId": "AK"}
    )  # BE-DETECTOR-5
    mock_detector.provider_name = "aws"

    # Mock RegionDiscovery
    mock_rd = MagicMock()
    mock_rd.get_enabled_regions = AsyncMock(return_value=["us-east-1"])

    with patch(
        "app.modules.optimization.domain.factory.ZombieDetectorFactory.get_detector",
        return_value=mock_detector,
    ):
        with patch(
            "app.modules.optimization.adapters.aws.region_discovery.RegionDiscovery",
            return_value=mock_rd,
        ):
            with patch(
                "app.modules.optimization.domain.service.is_feature_enabled",
                return_value=False,
            ):  # Skip AI
                with patch(
                    "app.shared.core.pricing.get_tenant_tier",
                    AsyncMock(return_value="starter"),
                ):  # BE-PRICING-5
                    with patch(
                        "app.shared.core.notifications.NotificationDispatcher.notify_zombies",
                        new_callable=AsyncMock,
                    ):
                        with patch("app.shared.core.ops_metrics.SCAN_LATENCY"):
                            results = await zombie_service.scan_for_tenant(
                                tenant_id, user
                            )

                            assert (
                                results["total_monthly_waste"] == 60.0
                            )  # 30 (aws) + 30 (gcp)
                            assert (
                                len(results["unattached_volumes"]) == 2
                            )  # 1 from each
                            assert results["scanned_connections"] == 2
                            assert results["waste_rightsizing"]["deterministic"] is True
                            assert (
                                results["waste_rightsizing"]["summary"][
                                    "total_recommendations"
                                ]
                                == 4
                            )
                            assert (
                                results["architectural_inefficiency"]["deterministic"]
                                is True
                            )


@pytest.mark.asyncio
async def test_scan_for_tenant_timeout_handling(zombie_service, db_session):
    tenant_id = uuid4()
    user = MagicMock(tenant_id=tenant_id)
    aws_conn = AWSConnection(id=uuid4(), tenant_id=tenant_id)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.side_effect = [[aws_conn], [], []]
    db_session.execute.return_value = mock_res

    mock_detector = MagicMock()
    mock_detector.scan_all = AsyncMock()
    with patch(
        "app.modules.optimization.domain.factory.ZombieDetectorFactory.get_detector",
        return_value=mock_detector,
    ):
        with patch("app.shared.core.ops_metrics.SCAN_TIMEOUTS"):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                results = await zombie_service.scan_for_tenant(tenant_id, user)
                assert results.get("scan_timeout") is True
                assert results.get("partial_results") is True


@pytest.mark.asyncio
async def test_ai_enrichment_tier_gating(zombie_service, db_session):
    tenant_id = uuid4()
    MagicMock(tenant_id=tenant_id, tier="free")
    zombies = {"unattached_volumes": []}

    with patch(
        "app.modules.optimization.domain.service.is_feature_enabled", return_value=False
    ):
        from app.shared.core.pricing import PricingTier

        await zombie_service._enrich_with_ai(zombies, tenant_id, PricingTier.STARTER)
        assert "upgrade_required" in zombies["ai_analysis"]


@pytest.mark.asyncio
async def test_ai_enrichment_failure_handling(zombie_service, db_session):
    tenant_id = uuid4()
    MagicMock(tenant_id=tenant_id, tier="growth")
    zombies = {"unattached_volumes": []}

    with patch(
        "app.modules.optimization.domain.service.is_feature_enabled", return_value=True
    ):
        with patch(
            "app.shared.llm.factory.LLMFactory.create",
            side_effect=Exception("LLM Down"),
        ):
            from app.shared.core.pricing import PricingTier

            await zombie_service._enrich_with_ai(zombies, tenant_id, PricingTier.GROWTH)
            assert "AI analysis failed" in zombies["ai_analysis"]["error"]


@pytest.mark.asyncio
async def test_parallel_scan_exception_handling(zombie_service, db_session):
    tenant_id = uuid4()
    user = MagicMock(tenant_id=tenant_id)
    aws_conn = AWSConnection(id=uuid4(), tenant_id=tenant_id)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.side_effect = [[aws_conn], [], []]
    db_session.execute.return_value = mock_res

    mock_detector = MagicMock()
    mock_detector.provider_name = "aws"
    mock_detector.scan_all = AsyncMock(side_effect=Exception("Provider Failure"))

    with patch(
        "app.modules.optimization.domain.factory.ZombieDetectorFactory.get_detector",
        return_value=mock_detector,
    ):
        results = await zombie_service.scan_for_tenant(tenant_id, user)
        # Should finish successfully but with 0 waste due to error in provider
        assert results["total_monthly_waste"] == 0.0
