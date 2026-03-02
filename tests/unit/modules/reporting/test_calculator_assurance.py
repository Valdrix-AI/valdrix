from app.modules.reporting.domain.calculator import CarbonCalculator


def test_calculation_includes_methodology_metadata() -> None:
    calculator = CarbonCalculator()
    result = calculator.calculate_from_costs(
        cost_data=[
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {"UnblendedCost": {"Amount": "100.00"}},
                    }
                ]
            }
        ],
        region="us-east-1",
        provider="aws",
    )

    metadata = result["methodology_metadata"]
    assert metadata["methodology_version"] == "valdrics-carbon-v2.0"
    assert metadata["provider"] == "aws"
    assert metadata["factor_source"]
    assert metadata["factor_version"]
    assert metadata["factor_timestamp"]
    assert len(metadata["factors_checksum_sha256"]) == 64
    assert len(metadata["calculation_input_checksum_sha256"]) == 64


def test_calculation_input_checksum_is_reproducible_for_same_inputs() -> None:
    calculator = CarbonCalculator()
    cost_data = [
        {
            "Groups": [
                {
                    "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                    "Metrics": {"UnblendedCost": {"Amount": "50.00"}},
                }
            ]
        }
    ]
    first = calculator.calculate_from_costs(
        cost_data=cost_data, region="eu-west-1", provider="aws"
    )
    second = calculator.calculate_from_costs(
        cost_data=cost_data, region="eu-west-1", provider="aws"
    )

    assert (
        first["methodology_metadata"]["calculation_input_checksum_sha256"]
        == second["methodology_metadata"]["calculation_input_checksum_sha256"]
    )


def test_provider_aware_factor_selection_changes_energy_estimate() -> None:
    calculator = CarbonCalculator()
    grouped_cost_data = [
        {
            "Groups": [
                {
                    "Keys": ["Virtual Machines"],
                    "Metrics": {"UnblendedCost": {"Amount": "100.00"}},
                }
            ]
        }
    ]

    azure_result = calculator.calculate_from_costs(
        cost_data=grouped_cost_data,
        region="eu-west-1",
        provider="azure",
    )
    aws_result = calculator.calculate_from_costs(
        cost_data=grouped_cost_data,
        region="eu-west-1",
        provider="aws",
    )

    assert azure_result["provider"] == "azure"
    assert aws_result["provider"] == "aws"
    assert azure_result["estimated_energy_kwh"] > aws_result["estimated_energy_kwh"]
