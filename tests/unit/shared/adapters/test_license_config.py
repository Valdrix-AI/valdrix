from app.shared.adapters.license_config import parse_google_workspace_license_config


def test_parse_google_workspace_license_config_parses_explicit_values() -> None:
    parsed = parse_google_workspace_license_config(
        {
            "sku_prices": {
                "Google-Apps-For-Business": "12.5",
                "1010020027": 18,
                "": 2,
                7: 9,
            },
            "default_seat_price_usd": "14.0",
            "currency": "ngn",
        }
    )

    assert parsed.sku_prices_usd == {
        "Google-Apps-For-Business": 12.5,
        "1010020027": 18.0,
    }
    assert parsed.default_seat_price_usd == 14.0
    assert parsed.currency == "NGN"
    assert parsed.target_skus == ["Google-Apps-For-Business", "1010020027"]


def test_parse_google_workspace_license_config_uses_safe_defaults() -> None:
    parsed = parse_google_workspace_license_config(
        {
            "sku_prices": "invalid",
            "default_seat_price_usd": None,
            "currency": None,
        }
    )

    assert parsed.sku_prices_usd == {}
    assert parsed.default_seat_price_usd == 12.0
    assert parsed.currency == "USD"
    assert parsed.target_skus == ["Google-Apps-For-Business", "1010020027"]
