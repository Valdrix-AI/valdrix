# Valdrix Deprecation & Versioning Policy

To ensure high reliability for enterprise customers, Valdrix follows strict version lifecycles.

## 1. API Versioning
- **Structure**: `/api/v[N]/` (e.g., `/api/v1/`).
- **Breaking Changes**: New breaking changes must increment the major version.
- **Support Window**: The previous major version is supported for 12 months after a new version release.

## 2. Feature Deprecation Process
1. **Notice**: Deprecation is announced via API response headers (`X-Deprecated-At`) and email.
2. **Warning Period**: Feature remains active for 90 days with warnings in logs/dashboard.
3. **Brownout**: Feature is disabled for short periods (1-4 hours) to identify silent dependencies.
4. **Sunset**: Feature is permanently removed.

## 3. SDK & Internal Contract Stability
- Pydantic models in `app/schemas` are considered stable.
- Private methods (prefixed with `_`) are subject to change without notice.
