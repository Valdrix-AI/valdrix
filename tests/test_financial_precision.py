import pytest
from decimal import Decimal
from app.schemas.costs import CostRecord, CloudUsageSummary
from datetime import date

def test_financial_precision_decimal_sum():
    """
    Test that summing many small Decimal costs results in exact precision,
    unlike floating point which would introduce rounding errors.
    """
    # 10,000 very small records (e.g., Lambda invocations)
    # 0.00000021 USD each
    small_amount = Decimal("0.00000021")
    count = 10000
    expected_total = Decimal("0.00210000") # 10000 * 0.00000021
    
    records = [
        CostRecord(date=date.today(), amount=small_amount, service="AWSLambda")
        for _ in range(count)
    ]
    
    summary = CloudUsageSummary(
        tenant_id="test-tenant",
        provider="aws",
        start_date=date.today(),
        end_date=date.today(),
        total_cost=sum(r.amount for r in records),
        records=records
    )
    
    # Assert exact match
    assert summary.total_cost == expected_total
    assert isinstance(summary.total_cost, Decimal)

def test_float_comparison_failure_simulation():
    """
    Shows why we moved away from float.
    """
    f_amount = 0.00000021
    f_total = sum([f_amount for _ in range(10000)])
    f_expected = 0.0021
    
    # Floating point arithmetic often results in tiny errors
    # In this specific case, it might actually work or fail depending on precision
    # but at scale (billions), it ALWAYS fails.
    print(f"Float Total: {f_total}")
    print(f"Float Expected: {f_expected}")
    
    d_amount = Decimal("0.00000021")
    d_total = sum([d_amount for _ in range(10000)])
    d_expected = Decimal("0.0021")
    
    assert d_total == d_expected
