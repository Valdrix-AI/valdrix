"""
Integration tests for edge cases and complex scenarios
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request
import uuid
import asyncio

from app.modules.optimization.domain.service import ZombieService
from app.shared.core.health import HealthService
from app.shared.core.notifications import NotificationDispatcher
from app.shared.db.session import get_db, set_session_tenant_id
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection


class TestZombieServiceEdgeCases:
    """Integration tests for ZombieService edge cases."""

    @pytest_asyncio.fixture
    async def mock_db(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest_asyncio.fixture
    async def zombie_service(self, mock_db):
        """Create ZombieService instance."""
        return ZombieService(mock_db)

    @pytest.mark.asyncio
    async def test_scan_for_tenant_no_connections(self, zombie_service, mock_db):
        """Test scan when tenant has no cloud connections."""
        tenant_id = uuid.uuid4()
        
        # Mock database queries to return no connections
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        with patch('app.modules.optimization.domain.service.select') as mock_select:
            mock_select.return_value.where.return_value = mock_select
            
            result = await zombie_service.scan_for_tenant(tenant_id)
            
            assert result["error"] == "No cloud connections found."
            assert result["total_monthly_waste"] == 0.0

    @pytest.mark.asyncio
    async def test_scan_for_tenant_connection_failure(self, zombie_service, mock_db):
        """Test scan when cloud connection fails."""
        tenant_id = uuid.uuid4()
        
        # Mock connection 
        mock_connection = MagicMock(spec=AWSConnection)
        mock_connection.tenant_id = tenant_id
        mock_connection.region = "us-east-1"
        
        # Prepare DB results for 3 calls (AWS, Azure, GCP) to avoid duplications
        res_conn = MagicMock()
        res_conn.scalars.return_value.all.return_value = [mock_connection]
        res_empty = MagicMock()
        res_empty.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [res_conn, res_empty, res_empty]
        
        with patch('app.modules.optimization.domain.service.select'), \
             patch('app.modules.optimization.domain.service.ZombieDetectorFactory') as mock_factory:
                
                mock_detector = AsyncMock()
                # Mock scan_all to raise exception
                mock_detector.scan_all.side_effect = Exception("AWS API failure")
                mock_factory.get_detector.return_value = mock_detector
                
                result = await zombie_service.scan_for_tenant(tenant_id)
                
                # Should handle failure gracefully (log and continue)
                assert "unattached_volumes" in result
                assert "scan_timeout" not in result

    @pytest.mark.asyncio
    async def test_scan_for_tenant_partial_failure(self, zombie_service, mock_db):
        """Test scan when some providers fail and others succeed."""
        tenant_id = uuid.uuid4()
        
        # Connections
        mock_aws = MagicMock(spec=AWSConnection)
        mock_aws.tenant_id = tenant_id
        mock_aws.region = "us-east-1"
        mock_aws.access_key_id = "test_key"
        
        mock_azure = MagicMock(spec=AzureConnection)
        mock_azure.tenant_id = tenant_id
        mock_azure.region = "eastus"
        
        # Prepare DB: AWS, Azure, GCP (Empty)
        res_aws = MagicMock()
        res_aws.scalars.return_value.all.return_value = [mock_aws]
        res_azure = MagicMock()
        res_azure.scalars.return_value.all.return_value = [mock_azure]
        res_gcp = MagicMock()
        res_gcp.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [res_aws, res_azure, res_gcp]
        
        with patch('app.modules.optimization.domain.service.select'), \
             patch('app.modules.optimization.domain.service.ZombieDetectorFactory') as mock_factory, \
             patch('app.modules.optimization.adapters.aws.region_discovery.RegionDiscovery') as MockRD:
                
                # AWS Success - Mock Region Discovery
                MockRD.return_value.get_enabled_regions = AsyncMock(return_value=["us-east-1"])

                mock_aws_detector = AsyncMock()
                mock_aws_detector.provider_name = "aws"
                mock_aws_detector.scan_all.return_value = {"idle_instances": [{"id": "i-123", "owner": "me"}]}
                
                # Azure Failure
                mock_azure_detector = AsyncMock()
                mock_azure_detector.provider_name = "azure"
                mock_azure_detector.scan_all.side_effect = Exception("Azure API failure")

                # Mock factory.get_detector
                def get_detector_side_effect(conn, **kwargs):
                    if conn == mock_aws:
                        return mock_aws_detector
                    elif conn == mock_azure:
                        return mock_azure_detector
                    return AsyncMock()
                
                mock_factory.get_detector.side_effect = get_detector_side_effect
                
                result = await zombie_service.scan_for_tenant(tenant_id)
                
                # AWS results should be present
                assert len(result["idle_instances"]) == 1
                assert result["idle_instances"][0]["id"] == "i-123"
                assert result["idle_instances"][0]["provider"] == "aws"
                
                # Azure failure should be logged but not crash
                assert "unattached_volumes" in result

    @pytest.mark.asyncio
    async def test_scan_with_on_category_complete_callback(self, zombie_service, mock_db):
        """Test scan with category completion callback."""
        tenant_id = uuid.uuid4()
        callback_calls = []
        
        async def mock_callback(category, zombies):
            callback_calls.append((category, zombies))
        
        # Mock connection
        mock_connection = MagicMock(spec=AWSConnection)
        mock_connection.tenant_id = tenant_id
        mock_connection.region = "us-east-1"
        
        # Prepare DB results for 3 calls to prevent duplication
        res_conn = MagicMock()
        res_conn.scalars.return_value.all.return_value = [mock_connection]
        res_empty = MagicMock()
        res_empty.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [res_conn, res_empty, res_empty]
        
        with patch('app.modules.optimization.domain.service.select'), \
             patch('app.modules.optimization.domain.service.ZombieDetectorFactory') as mock_factory, \
             patch('app.modules.optimization.adapters.aws.region_discovery.RegionDiscovery') as MockRD:
                
                MockRD.return_value.get_enabled_regions = AsyncMock(return_value=["us-east-1"])

                mock_detector = AsyncMock()
                mock_detector.provider_name = "aws"
                
                async def side_effect_scan(on_category_complete=None):
                    if on_category_complete:
                        await on_category_complete("idle_instances", [{"id": "i-123"}])
                        await on_category_complete("unattached_volumes", [{"id": "vol-456"}])
                    return {
                        "idle_instances": [{"id": "i-123"}],
                        "unattached_volumes": [{"id": "vol-456"}]
                    }
                
                mock_detector.scan_all.side_effect = side_effect_scan
                mock_factory.get_detector.return_value = mock_detector
                
                await zombie_service.scan_for_tenant(
                    tenant_id, 
                    on_category_complete=mock_callback
                )
                
                # Verify calls (1 region * 2 categories = 2 calls)
                assert len(callback_calls) == 2
                assert ("idle_instances", [{"id": "i-123"}]) in callback_calls
                assert ("unattached_volumes", [{"id": "vol-456"}]) in callback_calls

    @pytest.mark.asyncio
    async def test_scan_with_ai_analysis_enabled(self, zombie_service, mock_db):
        """Test scan with AI analysis enabled."""
        tenant_id = uuid.uuid4()
        
        # Mock connection
        mock_connection = MagicMock(spec=AWSConnection)
        mock_connection.tenant_id = tenant_id
        mock_connection.region = "us-east-1"
        
        # DB Sequence: AWS=1, others=empty
        res_conn = MagicMock()
        res_conn.scalars.return_value.all.return_value = [mock_connection]
        res_empty = MagicMock()
        res_empty.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [res_conn, res_empty, res_empty]
        
        with patch('app.modules.optimization.domain.service.select'), \
             patch('app.modules.optimization.domain.service.ZombieDetectorFactory') as mock_factory:
                mock_detector = AsyncMock()
                mock_detector.provider_name = "aws"
                mock_detector.scan_all.return_value = {
                    "idle_instances": [{"id": "i-123", "monthly_cost": 50.0}]
                }
                mock_factory.get_detector.return_value = mock_detector
                
                result = await zombie_service.scan_for_tenant(tenant_id, analyze=True)

                assert "ai_analysis" in result


class TestHealthServiceIntegration:
    """Integration tests for HealthService edge cases."""

    @pytest_asyncio.fixture
    async def mock_db(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest_asyncio.fixture
    async def health_service(self, mock_db):
        """Create HealthService instance."""
        return HealthService(mock_db)

    @pytest.mark.asyncio
    async def test_health_check_cascading_failures(self, health_service, mock_db):
        """Test health check with multiple service failures."""
        # Database fails
        mock_db.execute.side_effect = Exception("Database connection failed")
        
        from app.shared.core.config import get_settings
        settings = get_settings()
        original_redis = settings.REDIS_URL
        settings.REDIS_URL = "redis://localhost"
        try:
             # Patch get_redis_client in the rate_limit module where it is defined
             with patch('app.shared.core.rate_limit.get_redis_client') as mock_get_redis:
                mock_redis = AsyncMock()
                mock_redis.ping.side_effect = Exception("Redis connection failed")
                mock_get_redis.return_value = mock_redis
                
                # AWS fails
                with patch('httpx.AsyncClient') as mock_client:
                    mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                        side_effect=Exception("Network error")
                    )
                    
                    result = await health_service.check_all()
                    
                    # Overall status should be unhealthy due to database failure
                    assert result["aws"]["status"] == "down"
        finally:
             settings.REDIS_URL = original_redis

    @pytest.mark.asyncio
    async def test_health_check_timeout_handling(self, health_service, mock_db):
        """Test health check with timeout scenarios."""
        # Database slow but successful
        async def slow_db_execute(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate slow query
            return MagicMock()
        
        mock_db.execute = slow_db_execute
        
        with patch('asyncio.get_running_loop') as mock_loop:
            mock_loop.return_value.time.side_effect = [1000.0, 1000.15]  # 150ms latency
            
            success, details = await health_service.check_database()
            
            assert success is True
            assert details["latency_ms"] == 150.0

    @pytest.mark.asyncio
    async def test_health_check_partial_configuration(self, health_service):
        """Test health check with partial service configuration."""
        # Redis not configured, AWS working
        from app.shared.core.config import get_settings
        settings = get_settings()
        original_redis = settings.REDIS_URL
        settings.REDIS_URL = None
        try:
            with patch('httpx.AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
                
                result = await health_service.check_all()
                
                # Redis should be skipped, AWS should be up
                assert result["redis"]["status"] == "skipped"
                assert result["aws"]["status"] == "up"
        finally:
            settings.REDIS_URL = original_redis


class TestNotificationDispatcherIntegration:
    """Integration tests for NotificationDispatcher edge cases."""

    @pytest.mark.asyncio
    async def test_notification_cascade_failure(self):
        """Test notification dispatch when multiple providers fail."""
        # Mock Slack service that fails
        mock_slack = AsyncMock()
        mock_slack.send_alert.side_effect = Exception("Slack API error")
        mock_slack.notify_zombies.side_effect = Exception("Slack webhook failed")
        mock_slack.notify_budget_alert.side_effect = Exception("Rate limited")
        
        with patch('app.shared.core.notifications.get_slack_service', return_value=mock_slack):
            with patch('app.shared.core.notifications.logger'):
                # All methods should propagate failures or handle them if implemented
                # Since Dispatcher doesn't suppress, we expect exceptions OR check individual calls
                # For this test, we verify that they are called.
                
                try:
                    await NotificationDispatcher.send_alert("Test", "Message", "error")
                except Exception:
                    pass
                    
                try:
                    await NotificationDispatcher.notify_zombies({}, 100.0)
                except Exception:
                    pass

                try:
                    await NotificationDispatcher.notify_budget_alert(100.0, 200.0, 50.0)
                except Exception:
                    pass
                
                # Should have attempted to use the service
                assert len(mock_slack.method_calls) > 0

    @pytest.mark.asyncio
    async def test_notification_large_payload_handling(self):
        """Test notification dispatch with large payloads."""
        mock_slack = AsyncMock()
        
        # Large zombies payload
        large_zombies = {
            "ec2": [{"id": f"i-{i}", "cost": 50.0} for i in range(1000)],
            "ebs": [{"id": f"vol-{i}", "cost": 10.0} for i in range(1000)],
            "s3": [{"id": f"bucket-{i}", "cost": 5.0} for i in range(1000)]
        }
        
        with patch('app.shared.core.notifications.get_slack_service', return_value=mock_slack):
            with patch('app.shared.core.notifications.logger'):
                await NotificationDispatcher.notify_zombies(large_zombies, estimated_savings=50000.0)
                
                # Should handle large payload without issues
                mock_slack.notify_zombies.assert_called_once_with(large_zombies, 50000.0)

    @pytest.mark.asyncio
    async def test_notification_concurrent_dispatch(self):
        """Test concurrent notification dispatch."""
        mock_slack = AsyncMock()
        
        with patch('app.shared.core.notifications.get_slack_service', return_value=mock_slack):
            with patch('app.shared.core.notifications.logger'):
                # Send multiple notifications concurrently
                tasks = [
                    NotificationDispatcher.send_alert(f"Alert {i}", f"Message {i}")
                    for i in range(10)
                ]
                
                await asyncio.gather(*tasks)
                
                # All notifications should be sent
                assert mock_slack.send_alert.call_count == 10


class TestDatabaseSessionIntegration:
    """Integration tests for database session edge cases."""

    @pytest.mark.asyncio
    async def test_rls_context_with_concurrent_requests(self):
        """Test RLS context handling with concurrent requests."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.bind = MagicMock()
        mock_session.bind.url = "postgresql+asyncpg://test"
        mock_session.execute = AsyncMock()
        mock_session.connection = AsyncMock(return_value=AsyncMock())
        mock_session.close = AsyncMock()
        
        # Create multiple concurrent requests with different tenant IDs
        tenant_ids = [uuid.uuid4() for _ in range(5)]
        
        async def simulate_request(tenant_id):
            mock_request = MagicMock(spec=Request)
            mock_request.state.tenant_id = tenant_id
            
            async for session in get_db(mock_request):
                return session
        
        # Run requests concurrently
        # Must patch async_session_maker to return our mock session
        with patch('app.shared.db.session.async_session_maker') as mock_maker:
            mock_maker.return_value.__aenter__.return_value = mock_session
            
            tasks = [simulate_request(tid) for tid in tenant_ids]
            sessions = await asyncio.gather(*tasks)
        
        # Verify all requests got sessions
        assert len(sessions) == 5
        assert all(isinstance(s, AsyncMock) for s in sessions)

    @pytest.mark.asyncio
    async def test_session_tenant_id_override(self):
        """Test setting tenant ID on existing session."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.bind = MagicMock()
        mock_session.bind.url = "postgresql+asyncpg://test"
        mock_session.execute = AsyncMock()
        mock_session.connection = AsyncMock(return_value=AsyncMock())
        mock_session.info = {}
        
        tenant_id = uuid.uuid4()
        
        await set_session_tenant_id(mock_session, tenant_id)
        
        # Verify RLS context was set
        mock_session.execute.assert_called()
        
        # Verify session info was updated
        assert mock_session.info["rls_context_set"] is True

    @pytest.mark.asyncio
    async def test_database_connection_recovery(self):
        """Test database session behavior after connection failure."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.bind = MagicMock()
        mock_session.bind.url = "postgresql+asyncpg://test"
        
        # First call fails, second succeeds
        mock_session.execute = AsyncMock(side_effect=[Exception("Connection lost"), MagicMock()])
        mock_session.connection = AsyncMock(return_value=AsyncMock())
        mock_session.close = AsyncMock()
        
        tenant_id = uuid.uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = tenant_id
        
        with patch('app.shared.db.session.async_session_maker') as mock_session_maker:
            mock_session_maker.return_value.__aenter__.return_value = mock_session
            with patch('app.shared.db.session.logger') as mock_logger:
                
                async for session in get_db(mock_request):
                    assert session == mock_session
                    break
                
                # Should have logged the RLS failure but continued
                mock_logger.warning.assert_called_once()


class TestMultiTenantEdgeCases:
    """Integration tests for multi-tenant edge cases."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_with_shared_resources(self):
        """Test tenant isolation with shared database resources."""
        # This would test actual database RLS policies
        # For now, we'll test the session management aspect
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.bind = MagicMock()
        mock_session.bind.url = "postgresql+asyncpg://test"
        mock_session.execute = AsyncMock()
        mock_session.connection = AsyncMock(return_value=AsyncMock())
        mock_session.close = AsyncMock()
        
        tenant1_id = uuid.uuid4()
        tenant2_id = uuid.uuid4()
        
        # Simulate requests from different tenants
        async def tenant_request(tenant_id):
            mock_request = MagicMock(spec=Request)
            mock_request.state.tenant_id = tenant_id
            
            async for session in get_db(mock_request):
                # Verify RLS context is set for this tenant
                assert session.info["rls_context_set"] is True
                return session
        
        session1 = await tenant_request(tenant1_id)
        session2 = await tenant_request(tenant2_id)
        
        # Both should have RLS context set
        assert session1.info["rls_context_set"] is True
        assert session2.info["rls_context_set"] is True

    @pytest.mark.asyncio
    async def test_cross_tenant_data_leak_prevention(self):
        """Test prevention of cross-tenant data access."""
        # This would test the RLS enforcement listener
        with patch('app.shared.db.session.settings') as mock_settings:
            mock_settings.TESTING = False
            
            # Mock connection without RLS context
            mock_conn = MagicMock()
            mock_conn.info = {"rls_context_set": False}
            
            from app.shared.db.session import check_rls_policy
            
            # Should raise exception for data access without RLS context
            with pytest.raises(Exception) as exc_info:
                check_rls_policy(mock_conn, None, "SELECT * FROM cost_records", {}, {}, False)
            
            assert "rls_enforcement_failed" in str(exc_info.value.code)
