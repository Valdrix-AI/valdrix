# FOCUS Export (v1.3 Core CSV)

Valdrics supports a **FOCUS v1.3-aligned core export** for cost records in the tenant ledger.

This export is intentionally scoped to the FOCUS columns that Valdrics can derive deterministically
from the normalized cost ledger today, without claiming SKU or unit-price conformance for fields
we do not persist yet.

## Endpoint

`GET /api/v1/costs/export/focus`

Query parameters:
- `start_date` (required): `YYYY-MM-DD` (inclusive)
- `end_date` (required): `YYYY-MM-DD` (inclusive)
- `provider` (optional): one of `aws|azure|gcp|saas|license|platform|hybrid`
- `include_preliminary` (optional, default `false`): include `PRELIMINARY` records (otherwise exports `FINAL` only)

Auth / tier:
- Requires role: `admin` (or `owner`)
- Requires feature: `compliance_exports` (Pro+)

## Columns (Core)

The export includes the following columns:
- `BilledCost`
- `BillingAccountId`
- `BillingAccountName`
- `BillingCurrency`
- `BillingPeriodStart`
- `BillingPeriodEnd`
- `ChargeCategory`
- `ChargeClass`
- `ChargeDescription`
- `ChargeFrequency`
- `ChargePeriodStart`
- `ChargePeriodEnd`
- `ContractedCost`
- `EffectiveCost`
- `InvoiceIssuerName`
- `ListCost`
- `ProviderName`
- `PublisherName`
- `RegionId`
- `RegionName`
- `ServiceProviderName`
- `ServiceCategory`
- `ServiceSubcategory`
- `ServiceName`
- `Tags`

## Semantics

- `BillingPeriodStart` is computed as the first day of the record month at `00:00:00Z`.
- `BillingPeriodEnd` is computed as the first day of the next month at `00:00:00Z`.
- For AWS/Azure/GCP records, `ChargePeriodStart` is the record timestamp and `ChargePeriodEnd` is `+1 hour`.
- For Cloud+ records (SaaS/license/platform/hybrid), `ChargePeriodStart/End` are daily window bounds.

## Known Limitations (By Design for v1)

- SKU/unit price columns are not included yet (Valdrics does not persist those fields in the ledger today).
- ServiceSubcategory is currently exported as `Other (ServiceCategory)` until per-provider subcategory
  normalization is added.

