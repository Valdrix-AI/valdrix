#!/usr/bin/env bash
# OpenAPI TypeScript Client Generation Script
# Generates type-safe API client from FastAPI's OpenAPI spec

set -euo pipefail

# Configuration
API_URL="${API_URL:-https://api.valdrics.ai}"
OPENAPI_URL="${API_URL}/openapi.json"
OUTPUT_DIR="dashboard/src/lib/api"

if [[ ! "${API_URL}" =~ ^https?:// ]]; then
    echo "❌ API_URL must start with http:// or https://"
    exit 1
fi

if [[ "${API_URL}" =~ ^http:// ]] && [[ ! "${API_URL}" =~ ^http://(localhost|127\.0\.0\.1)(:[0-9]+)?$ ]]; then
    echo "❌ Non-local API_URL must use https://"
    exit 1
fi

api_host="$(printf '%s' "${API_URL}" | sed -E 's#^https?://([^/:]+).*#\1#')"
if [[ -n "${OPENAPI_ALLOWED_HOSTS:-}" ]]; then
    if ! printf '%s' "${OPENAPI_ALLOWED_HOSTS}" | tr ',' '\n' | grep -Fxq "${api_host}"; then
        echo "❌ API host '${api_host}' is not in OPENAPI_ALLOWED_HOSTS allowlist"
        exit 1
    fi
fi

echo "🔄 Generating TypeScript client from OpenAPI spec..."
echo "   Source: ${OPENAPI_URL}"
echo "   Output: ${OUTPUT_DIR}"

# Ensure output directory exists
mkdir -p "${OUTPUT_DIR}"

# Check if openapi-typescript-codegen is installed
if ! command -v openapi-generator-cli &> /dev/null; then
    echo "📦 Installing openapi-generator-cli..."
    npm install -g @openapitools/openapi-generator-cli
fi

# Fetch OpenAPI spec
echo "📥 Fetching OpenAPI specification..."
curl -sSf "${OPENAPI_URL}" -o /tmp/openapi.json

# Generate TypeScript client
echo "⚙️  Generating TypeScript client..."
openapi-generator-cli generate \
    -i /tmp/openapi.json \
    -g typescript-fetch \
    -o "${OUTPUT_DIR}" \
    --additional-properties=typescriptThreePlus=true,supportsES6=true,npmName=@valdrics/api-client

# Alternative: Use openapi-typescript for types only
# npm install -g openapi-typescript
# openapi-typescript /tmp/openapi.json -o "${OUTPUT_DIR}/types.ts"

echo "✅ TypeScript client generated successfully!"
echo ""
echo "Usage in SvelteKit:"
echo "  import { DefaultApi, Configuration } from '\$lib/api';"
echo ""
echo "  const api = new DefaultApi(new Configuration({"
echo "    basePath: 'http://localhost:8000',"
echo "    accessToken: token"
echo "  }));"
echo ""
echo "  const resources = await api.listResources();"
