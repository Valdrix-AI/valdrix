from __future__ import annotations

from pathlib import Path

from scripts.check_frontend_hygiene import run


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_safe_dashboard(repo_root: Path) -> None:
    _write(
        repo_root / "dashboard/svelte.config.js",
        """
export default {
  kit: {
    csp: {
      mode: 'hash',
      directives: {
        'default-src': ['self'],
        'style-src': ['self']
      }
    }
  }
};
""".strip(),
    )
    _write(
        repo_root / "dashboard/src/app.html",
        """
<!doctype html>
<html lang="en">
  <body>
    <div class="app-shell">%sveltekit.body%</div>
  </body>
</html>
""".strip(),
    )
    _write(
        repo_root / "dashboard/src/lib/SafeWidget.svelte",
        """
<button type="button">Safe</button>
""".strip(),
    )


def test_run_passes_for_hash_csp_without_transitions(tmp_path: Path) -> None:
    _seed_safe_dashboard(tmp_path)

    assert run(tmp_path) == 0


def test_run_fails_when_dashboard_csp_allows_unsafe_inline(
    tmp_path: Path,
    capsys,
) -> None:
    _seed_safe_dashboard(tmp_path)
    _write(
        tmp_path / "dashboard/svelte.config.js",
        """
export default {
  kit: {
    csp: {
      directives: {
        'style-src': ['self', 'unsafe-inline']
      }
    }
  }
};
""".strip(),
    )

    assert run(tmp_path) == 1
    assert "unsafe-inline" in capsys.readouterr().out


def test_run_fails_when_app_html_uses_inline_style(tmp_path: Path, capsys) -> None:
    _seed_safe_dashboard(tmp_path)
    _write(
        tmp_path / "dashboard/src/app.html",
        """
<!doctype html>
<html lang="en">
  <body>
    <div style="display: contents">%sveltekit.body%</div>
  </body>
</html>
""".strip(),
    )

    assert run(tmp_path) == 1
    assert "app.html must not include manual inline styles" in capsys.readouterr().out


def test_run_fails_when_svelte_transition_directive_is_present(
    tmp_path: Path,
    capsys,
) -> None:
    _seed_safe_dashboard(tmp_path)
    _write(
        tmp_path / "dashboard/src/lib/AnimatedWidget.svelte",
        """
<script>
  import { fade } from 'svelte/transition';
</script>

{#if true}
  <div transition:fade={{ duration: 150 }}>
    Animated
  </div>
{/if}
""".strip(),
    )

    assert run(tmp_path) == 1
    assert "Svelte transition directives are disallowed under strict CSP" in capsys.readouterr().out
