import os
import re

directories = [
    "app/modules/optimization/adapters/aws/plugins",
    "app/modules/optimization/adapters/azure/plugins",
    "app/modules/optimization/adapters/gcp/plugins",
    "app/modules/optimization/adapters/kubernetes/plugins",
    "app/modules/optimization/adapters/saas/plugins",
    "app/modules/optimization/adapters/license/plugins",
]

base_sig = """    async def scan(
        self,
        session: Any,
        region: str,
        credentials: Dict[str, str] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:"""

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Regex to capture `async def scan(...) -> ...:`
    pattern = re.compile(r'(\s+)async def scan\s*\([^)]+\)\s*->\s*List\[Dict\[str,\s*Any\]\]:', re.MULTILINE)

    def replacer(match):
        indent = match.group(1)
        # Fix the base signature indentation
        new_sig = base_sig.replace("    ", indent)
        return new_sig

    new_content, count = pattern.subn(replacer, content)

    if count > 0:
        # Also need to make sure `Dict` and `Any` and `List` are imported
        if "from typing import" in new_content:
            pass # Usually handled
            
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"Updated {filepath} ({count} replacements)")

for directory in directories:
    if not os.path.exists(directory):
        continue
    for filename in os.listdir(directory):
        if filename.endswith(".py"):
            process_file(os.path.join(directory, filename))
