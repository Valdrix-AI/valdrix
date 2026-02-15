import pytest
import pytest_asyncio
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from app.modules.optimization.domain.service import ZombieService
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.shared.core.pricing import PricingTier


@pytest_asyncio.fixture
async def zombie_service(db):
    return ZombieService(db)


@pytest.mark.asyncio
async def test_scan_for_tenant_no_connections(zombie_service, db):
    """Test scan when no connections exist."""
    tenant_id = uuid4()
    user = MagicMock(tenant_id=tenant_id)

    # Mock empty results for all connection types
    db.execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result

    results = await zombie_service.scan_for_tenant(tenant_id, user)
    assert results["error"] == "No cloud connections found."
    assert results["total_monthly_waste"] == 0.0


@pytest.mark.asyncio
async def test_scan_for_tenant_multi_provider(zombie_service, db):
    """Test scanning multiple providers and verifying category mapping."""
    tenant_id = uuid4()
    user = MagicMock(tenant_id=tenant_id, tier=PricingTier.ENTERPRISE)

    # Mock connections
    aws_conn = AWSConnection(id=uuid4(), tenant_id=tenant_id, region="us-east-1")
    setattr(aws_conn, "name", "AWS Test")
    azure_conn = AzureConnection(id=uuid4(), tenant_id=tenant_id, name="Azure Test")

    async def mock_execute(query):
        res = MagicMock()
        if "aws_connections" in str(query):
            res.scalars.return_value.all.return_value = [aws_conn]
        elif "azure_connections" in str(query):
            res.scalars.return_value.all.return_value = [azure_conn]
        else:
            res.scalars.return_value.all.return_value = []
        return res

    db.execute = AsyncMock(side_effect=mock_execute)

    # Mock Tiers and Regions
    with patch(
        "app.shared.core.pricing.get_tenant_tier",
        AsyncMock(return_value=PricingTier.ENTERPRISE),
    ):
        with patch(
            "app.modules.optimization.adapters.aws.region_discovery.RegionDiscovery"
        ) as mock_rd_class:
            mock_rd = MagicMock()
            mock_rd.get_enabled_regions = AsyncMock(return_value=["us-east-1"])
            mock_rd_class.return_value = mock_rd

            # Mock Detectors
            with patch(
                "app.modules.optimization.domain.factory.ZombieDetectorFactory.get_detector"
            ) as mock_factory:
                # AWS Detector
                mock_aws_detector = AsyncMock()
                mock_aws_detector.provider_name = "aws"
                mock_aws_detector.scan_all.return_value = {
                    "unattached_volumes": [{"id": "vol-1", "monthly_waste": 10.0}],
                    "idle_instances": [{"id": "i-1", "monthly_waste": 50.0}],
                }
                # AWS regional scan needs credentials
                mock_aws_detector.get_credentials = AsyncMock(
                    return_value={"AccessKeyId": "test"}
                )

                # Azure Detector
                mock_azure_detector = AsyncMock()
                mock_azure_detector.provider_name = "azure"
                mock_azure_detector.scan_all.return_value = {
                    "unattached_disks": [{"id": "disk-1", "monthly_waste": 20.0}],
                    "orphaned_ips": [{"id": "ip-1", "monthly_waste": 5.0}],
                }

                # Setup factory to return AWS then Azure
                # Note: AWS is called twice (once for temp_detector, once for regional)
                mock_factory.side_effect = [
                    mock_aws_detector,
                    mock_aws_detector,
                    mock_azure_detector,
                ]

                with patch.object(zombie_service, "_send_notifications", AsyncMock()):
                    results = await zombie_service.scan_for_tenant(tenant_id, user)

                    assert results["total_monthly_waste"] == 85.0
                    assert len(results["unattached_volumes"]) == 2  # vol-1 + disk-1
                    assert len(results["unused_elastic_ips"]) == 1  # ip-1
                    assert results["scanned_connections"] == 2


@pytest.mark.asyncio
async def test_enrich_with_ai_tier_restriction(zombie_service):
    """Test AI enrichment block for low tiers."""
    user = MagicMock(tier=PricingTier.FREE_TRIAL)
    zombies = {"total_monthly_waste": 100.0}

    await zombie_service._enrich_with_ai(zombies, user.tenant_id, user.tier)
    assert zombies["ai_analysis"]["upgrade_required"] is True
    assert "requires Growth tier" in zombies["ai_analysis"]["error"]


@pytest.mark.asyncio
async def test_enrich_with_ai_success(zombie_service):
    """Test successful AI enrichment."""
    user = MagicMock(tier=PricingTier.ENTERPRISE, tenant_id=uuid4())
    zombies = {"total_monthly_waste": 100.0}

    with patch(
        "app.shared.llm.zombie_analyzer.ZombieAnalyzer.analyze", new_callable=AsyncMock
    ) as mock_analyze:
        mock_analyze.return_value = {"summary": "Kill them all"}
        with patch("app.shared.llm.factory.LLMFactory.create", MagicMock()):
            await zombie_service._enrich_with_ai(zombies, user.tenant_id, user.tier)
            assert zombies["ai_analysis"]["summary"] == "Kill them all"


@pytest.mark.asyncio
async def test_scan_provider_error_handling(zombie_service, db):
    """Test that a failure in one provider doesn't kill the whole scan."""
    tenant_id = uuid4()
    user = MagicMock(tenant_id=tenant_id)

    aws_conn = AWSConnection(id=uuid4(), tenant_id=tenant_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.side_effect = [[aws_conn], [], []]
    db.execute = AsyncMock(return_value=mock_result)

    with patch(
        "app.modules.optimization.domain.factory.ZombieDetectorFactory.get_detector"
    ) as mock_factory:
        mock_detector = AsyncMock()
        mock_detector.scan_all.side_effect = Exception("Cloud is down")
        mock_factory.return_value = mock_detector

        with patch.object(zombie_service, "_send_notifications", AsyncMock()):
            # Should NOT raise exception
            results = await zombie_service.scan_for_tenant(tenant_id, user)
            assert results["scanned_connections"] == 1
            assert results["total_monthly_waste"] == 0.0
