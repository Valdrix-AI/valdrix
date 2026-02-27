from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.aws.network import AWSDeleteLoadBalancerAction
from app.modules.optimization.domain.actions.base import (
    ExecutionStatus,
    RemediationContext,
)


class _AsyncClientContext:
    def __init__(self, client: object) -> None:
        self._client = client

    async def __aenter__(self) -> object:
        return self._client

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


@pytest.mark.asyncio
async def test_aws_delete_load_balancer_action_perform_action_success() -> None:
    action = AWSDeleteLoadBalancerAction()
    elb = MagicMock()
    elb.delete_load_balancer = AsyncMock()
    action._get_client = AsyncMock(return_value=_AsyncClientContext(elb))

    context = RemediationContext(
        tenant_id=uuid4(),
        region="us-east-1",
        tier="pro",
        credentials={"aws_access_key_id": "ak", "aws_secret_access_key": "sk"},
    )
    arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/lb/abc"

    result = await action._perform_action(arn, context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.resource_id == arn
    assert result.action_taken == RemediationAction.DELETE_LOAD_BALANCER.value
    action._get_client.assert_awaited_once_with("elbv2", context)
    elb.delete_load_balancer.assert_awaited_once_with(LoadBalancerArn=arn)
