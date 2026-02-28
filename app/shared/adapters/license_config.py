from dataclasses import dataclass
from typing import Any

from app.shared.adapters.feed_utils import as_float


@dataclass(frozen=True, slots=True)
class GoogleWorkspaceLicenseConfig:
    sku_prices_usd: dict[str, float]
    default_seat_price_usd: float
    currency: str
    target_skus: list[str]


def parse_google_workspace_license_config(
    connector_config: dict[str, Any],
) -> GoogleWorkspaceLicenseConfig:
    sku_prices_raw = connector_config.get("sku_prices")
    sku_prices: dict[str, float] = {}
    if isinstance(sku_prices_raw, dict):
        for key, value in sku_prices_raw.items():
            if isinstance(key, str) and key.strip():
                sku_prices[key.strip()] = as_float(value)

    default_price = as_float(
        connector_config.get("default_seat_price_usd"),
        default=12.0,  # Business Standard fallback
    )
    currency = str(connector_config.get("currency") or "USD").upper()
    target_skus = list(sku_prices.keys()) or [
        "Google-Apps-For-Business",
        "1010020027",
    ]

    return GoogleWorkspaceLicenseConfig(
        sku_prices_usd=sku_prices,
        default_seat_price_usd=default_price,
        currency=currency,
        target_skus=target_skus,
    )
