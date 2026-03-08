from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_network_module_uses_one_nat_gateway_per_private_subnet_az() -> None:
    text = (REPO_ROOT / "terraform/modules/network/main.tf").read_text(
        encoding="utf-8"
    )

    assert 'resource "aws_eip" "nat" {' in text
    assert "count  = length(var.private_subnet_cidrs)" in text
    assert 'resource "aws_nat_gateway" "main" {' in text
    assert "aws_nat_gateway.main[count.index].id" in text
    assert "aws_route_table.private[count.index].id" in text
    assert "precondition" in text


def test_cache_module_enables_multi_az_failover() -> None:
    text = (REPO_ROOT / "terraform/modules/cache/main.tf").read_text(
        encoding="utf-8"
    )

    assert "num_cache_clusters         = 2" in text
    assert "automatic_failover_enabled = true" in text
    assert "multi_az_enabled           = true" in text


def test_db_module_enables_multi_az_rds() -> None:
    text = (REPO_ROOT / "terraform/modules/db/main.tf").read_text(encoding="utf-8")

    assert "multi_az                     = true" in text
    assert 'contains(["prod", "production"], lower(var.environment))' in text
