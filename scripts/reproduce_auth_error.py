import requests
import subprocess
import json
import sys


def get_token():
    print("Generating bearer token...")
    result = subprocess.run(
        ["uv", "run", "scripts/dev_bearer_token.py", "--hours", "1"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Failed to generate token:")
        print(result.stdout)
        print(result.stderr)
        sys.exit(1)

    # The script output is just the raw token string
    output = result.stdout.strip()
    if "." in output and len(output) > 100:
        return output

    print("Could not find token in output:")
    print(output)
    sys.exit(1)


def test_auth(token):
    url = "http://localhost:8000/api/v1/settings/profile"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print(f"Requesting {url}...")
    try:
        response = requests.get(url, headers=headers)
        print(f"Status Code: {response.status_code}")
        print("Response Body:")
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print(f"Request failed: {e}")


if __name__ == "__main__":
    token = get_token()
    test_auth(token)
