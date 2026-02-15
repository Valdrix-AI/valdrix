import ast
import os
import re

versions_dir = "migrations/versions"
revisions = {}
parents = set()

for f in os.listdir(versions_dir):
    if not f.endswith(".py"):
        continue
    with open(os.path.join(versions_dir, f)) as src:
        content = src.read()
        rev_match = re.search(
            r"^revision\s*[:\s]*[str\s=]*['\"]([^'\"]+)['\"]", content, re.MULTILINE
        )
        down_match = re.search(
            r"^down_revision\s*[:\s]*Union[^\s=]*\s*=\s*([^\n]+)", content, re.MULTILINE
        )
        if not down_match:
            down_match = re.search(
                r"^down_revision\s*=\s*([^\n]+)", content, re.MULTILINE
            )

        if rev_match:
            rev = rev_match.group(1)
            revisions[rev] = f
            if down_match:
                down = down_match.group(1).split("#")[0].strip()
                if down.startswith("(") or down.startswith("["):
                    try:
                        p_list = ast.literal_eval(down)
                        if isinstance(p_list, (list, tuple)):
                            for p in p_list:
                                parents.add(p)
                        else:
                            parents.add(p_list)
                    except (SyntaxError, ValueError, TypeError):
                        pass  # Skip malformed or non-literal down_revision
                else:
                    parents.add(down.strip("'\""))

heads = set(revisions.keys()) - parents
print("Minimal Heads:")
for h in sorted(heads):
    print(f"  {h} ({revisions[h]})")
