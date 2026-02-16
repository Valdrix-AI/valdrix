import ast
import os
import re

versions_dir = "migrations/versions"
graph = {}

for f in os.listdir(versions_dir):
    if not f.endswith(".py"):
        continue
    path = os.path.join(versions_dir, f)
    with open(path) as src:
        content = src.read()
        rev_match = re.search(
            r"^revision\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE
        )
        if not rev_match:
            rev_match = re.search(
                r"^revision[:\s]+str\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE
            )

        down_match = re.search(r"^down_revision\s*=\s*([^\n]+)", content, re.MULTILINE)
        if not down_match:
            down_match = re.search(
                r"^down_revision[:\s]+Union[^\s=]*\s*=\s*([^\n]+)",
                content,
                re.MULTILINE,
            )

        if rev_match:
            rev = rev_match.group(1)
            down = down_match.group(1).strip() if down_match else "None"
            # Cleanup down_revision
            down = down.split("#")[0].strip()
            if down.startswith("(") or down.startswith("["):
                try:
                    down = ast.literal_eval(down)
                except (SyntaxError, ValueError, TypeError):
                    down = "None"
            else:
                down = down.strip("'\"")
            graph[rev] = down

print("Migration Graph (Revision -> Parents):")
for r, d in sorted(graph.items()):
    print(f"  {r} -> {d}")

heads = set(graph.keys())
for d in graph.values():
    if isinstance(d, (list, tuple)):
        for p in d:
            if p in heads:
                heads.remove(p)
    elif d and d != "None" and d != "base":
        if d in heads:
            heads.remove(d)

print(f"\nPotential Heads ({len(heads)}):")
for h in sorted(heads):
    print(f"  {h}")
