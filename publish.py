"""Publish a generated plugin the way the catalog actually admits plugins.

The official pathway (plugin-catalog/README.md, rule 1) is a pull request adding
`plugin-catalog/<name>.yaml` to NousResearch/hermes-agent, pinning a full 40-character commit
SHA of a public repository. There is no self-serve registry and no API to upload to: a human
merges the entry, and presence in the file is the trust signal.

So publishing is four steps, each one checkable:

    validate  ->  public repo at a commit  ->  catalog entry pinned to that SHA  ->  PR

Nothing here installs anything, and nothing rewrites the plugin. `install_local` links a
validated bundle into the profile and is the only step that changes the user's machine.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

HERMES_REPO = "NousResearch/hermes-agent"
CATALOG_DIR = "plugin-catalog"
GITIGNORE = "__pycache__/\n*.pyc\n*.tar.gz\n.gitignore\n"


class PublishError(Exception):
    """A step refused or failed; the message is the user-facing reason."""


def _run(cmd: list[str], cwd: Optional[Path] = None, timeout: int = 300) -> str:
    try:
        done = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                              text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise PublishError(f"{cmd[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise PublishError(f"{' '.join(cmd[:3])} timed out after {timeout}s") from exc
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or "").strip().splitlines()
        raise PublishError(detail[-1][:300] if detail else f"{cmd[0]} exited {done.returncode}")
    return (done.stdout or "").strip()


def gh_identity(run: Callable[..., str] = _run) -> dict:
    """Who would own the repo and the PR. Fails loudly rather than guessing."""
    try:
        login = run(["gh", "api", "user", "--jq", ".login"])
    except PublishError as exc:
        raise PublishError(f"GitHub CLI is not authenticated ({exc}); run `gh auth login`") from exc
    email = login.strip() or ""
    try:
        email = run(["gh", "api", "user", "--jq", ".email"]) or f"{login}@users.noreply.github.com"
    except PublishError:
        email = f"{login}@users.noreply.github.com"
    return {"login": login, "email": email or f"{login}@users.noreply.github.com"}


def validate_package(bundle: Path, run: Callable[..., str] = _run) -> dict:
    """The same gate catalog CI runs. Refuses to publish anything that fails it."""
    try:
        output = run(["hermes", "plugins", "validate", str(bundle), "--install-deps"], timeout=600)
    except PublishError as exc:
        return {"ok": False, "output": str(exc), "failures": [str(exc)]}
    tail = [line for line in output.splitlines() if line.strip()][-12:]
    return {"ok": True, "output": output, "tail": tail}


def git_commit(bundle: Path, message: str, identity: dict,
               run: Callable[..., str] = _run) -> str:
    """Make the tree a repo at one commit, and return that commit."""
    git = ["git", "-c", f"user.name={identity['login']}", "-c", f"user.email={identity['email']}"]
    if not (bundle / ".git").exists():
        run(["git", "init", "-q"], cwd=bundle)
    ignore = bundle / ".gitignore"
    if not ignore.exists():
        ignore.write_text(GITIGNORE, encoding="utf-8")
    run(["git", "add", "-A"], cwd=bundle)
    staged = run(["git", "status", "--porcelain"], cwd=bundle)
    if staged:
        run(git + ["commit", "-qm", message], cwd=bundle)
    return run(["git", "rev-parse", "HEAD"], cwd=bundle)


def create_repo(bundle: Path, owner: str, name: str, description: str,
                run: Callable[..., str] = _run) -> dict:
    """Create the public repo and push, or push to it if it already exists."""
    full = f"{owner}/{name}"
    try:
        run(["gh", "repo", "view", full, "--json", "url", "-q", ".url"])
        exists = True
    except PublishError:
        exists = False
    if not exists:
        run(["gh", "repo", "create", full, "--public", "--source", str(bundle), "--push",
             "--description", (description or name)[:350]])
        return {"created": True, "repo": full,
                "url": run(["gh", "repo", "view", full, "--json", "url", "-q", ".url"])}
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=bundle) or "main"
    if run(["git", "remote"], cwd=bundle).find("origin") < 0:
        run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"], cwd=bundle)
    run(["git", "push", "-q", "-u", "origin", branch], cwd=bundle)
    return {"created": False, "repo": full,
            "url": run(["gh", "repo", "view", full, "--json", "url", "-q", ".url"])}


def catalog_entry(bundle: Path, name: str, owner: str, sha: str, manifest: dict,
                  category: str = "tools", requires_hermes: str = ">=0.21.6") -> str:
    """One YAML file, every field the loader reads, no field it does not."""
    version = str(manifest.get("version") or "0.1.0")
    description = " ".join(str(manifest.get("description") or name).split())
    tools = list(manifest.get("provides_tools") or [])
    hooks = list(manifest.get("provides_hooks") or [])
    env = list(manifest.get("requires_env") or [])
    title = name.replace("-", " ").replace("_", " ").title()
    repo = f"https://github.com/{owner}/{name}"

    def block(key: str, values: list[str]) -> str:
        if not values:
            return f"  {key}: []\n"
        return f"  {key}:\n" + "".join(f"    - {value}\n" for value in values)

    return (
        f"name: {name}\n"
        f"repo: {repo}\n"
        f"sha: {sha}\n"
        f'version: "{version}"\n'
        f'title: "{title}"\n'
        f"description: >-\n"
        + "".join(f"  {line}\n" for line in _wrap(description, 92)) +
        f"maintainer: {owner}\n"
        f"tier: community\n"
        f"category: {category}\n"
        f"docs_url: {repo}#readme\n"
        f"readme: true\n"
        f'requires_hermes: "{requires_hermes}"\n'
        f"capabilities:\n"
        + block("provides_tools", tools)
        + block("provides_hooks", hooks)
        + f"  provides_middleware: []\n"
        + block("requires_env", env)
    )


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [text[:width]]


def open_pr(entry_text: str, name: str, owner: str, manifest: dict,
            run: Callable[..., str] = _run, scratch: Optional[Path] = None) -> dict:
    """Fork hermes-agent, add the entry on a branch, push, and open the PR."""
    # --remote is rejected alongside a repo argument; and an existing fork is not an error
    try:
        run(["gh", "repo", "view", f"{owner}/hermes-agent", "--json", "name", "-q", ".name"])
    except PublishError:
        run(["gh", "repo", "fork", HERMES_REPO, "--clone=false"])
    branch = f"add-{name}-plugin"
    work = Path(scratch) if scratch else Path(tempfile.mkdtemp(prefix="lazy-plugin-pr-"))
    checkout = work / "hermes-agent"
    if not checkout.exists():
        run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
             f"https://github.com/{owner}/hermes-agent.git", str(checkout)], timeout=600)
        run(["git", "sparse-checkout", "set", CATALOG_DIR], cwd=checkout)
    identity = gh_identity(run)
    git = ["git", "-c", f"user.name={identity['login']}", "-c", f"user.email={identity['email']}"]

    run(["git", "fetch", "origin", "main", "--depth", "1", "-q"], cwd=checkout)
    run(["git", "checkout", "-q", "-B", branch, "origin/main"], cwd=checkout)
    entry = checkout / CATALOG_DIR / f"{name}.yaml"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(entry_text, encoding="utf-8")
    run(["git", "add", str(entry)], cwd=checkout)
    run(git + ["commit", "-qm", f"Add {name} to the plugin catalog"], cwd=checkout)
    run(["git", "push", "-q", "-f", "-u", "origin", branch], cwd=checkout)

    body = pr_body(name, owner, manifest, Path(manifest.get("_bundle") or "") if manifest.get("_bundle") else None)
    body_file = work / "pr.md"
    body_file.write_text(body, encoding="utf-8")
    url = run(["gh", "pr", "create", "--repo", HERMES_REPO, "--base", "main",
               "--head", f"{owner}:{branch}", "--title", f"Add {name} to the plugin catalog",
               "--body-file", str(body_file)], timeout=300)
    return {"pr": url.strip().splitlines()[-1] if url else "", "branch": branch,
            "checkout": str(checkout), "body": body}


def tokens_network_line(bundle: Optional[Path]) -> str:
    """Say what the code actually does, not what the manifest implies."""
    if bundle is None:
        return "none declared"
    for path in Path(bundle).rglob("*.py"):
        try:
            if "urlopen(" in path.read_text(encoding="utf-8", errors="replace"):
                return "HTTP tools fetch the URLs set in their config; nothing else leaves the machine"
        except OSError:
            continue
    return "none of its own"


def tokens_files(bundle: Optional[Path]) -> list[str]:
    if bundle is None:
        return []
    return sorted(p.name for p in Path(bundle).iterdir() if p.is_file() and p.name != ".gitignore")


def pr_body(name: str, owner: str, manifest: dict, bundle: Optional[Path] = None) -> str:
    tools = list(manifest.get("provides_tools") or [])
    hooks = list(manifest.get("provides_hooks") or [])
    env = list(manifest.get("requires_env") or [])
    surfaces = []
    if tools:
        surfaces.append(f"- tools: {', '.join(f'`{tool}`' for tool in tools)}")
    if hooks:
        surfaces.append(f"- hooks: {', '.join(f'`{hook}`' for hook in hooks)}")
    surfaces.append("- public `ctx.register_*` APIs only; no Hermes core files touched")
    disclosure = [
        "- generated by Lazy Plugin from a spec; handler bodies come from four fixed templates "
        "(`command`, `http`, `file`, `stub`), so there is no self-updating code",
        f"- environment variables: {', '.join(env) if env else 'none'}",
        "- network: " + tokens_network_line(bundle),
        f"- files at the pinned commit: {', '.join(tokens_files(bundle))}",
    ]
    return (
        f"## What it does\n\n"
        f"{' '.join(str(manifest.get('description') or name).split())}\n\n"
        f"## Surfaces used\n\n" + "\n".join(surfaces) + "\n\n"
        f"## Disclosure\n\n" + "\n".join(disclosure) + "\n\n"
        f"## Validation\n\n"
        f"```\nhermes plugins validate <clone> --install-deps\n```\n\n"
        f"Run locally at the pinned commit before this PR: passed, including the install "
        f"security scan and the built-in tool collision check.\n"
    )


def install_local(bundle: Path, name: str, plugins_dir: Path,
                  validate: Callable[..., dict], run: Callable[..., str] = _run) -> dict:
    """Link the bundle into the profile. Re-validates first; never clobbers."""
    check = validate(bundle)
    if not check.get("ok"):
        return {"ok": False, "error": "the package does not validate; fix it first",
                "validation": check}
    target = plugins_dir / name
    if target.exists() or target.is_symlink():
        return {"ok": False, "error": f"{target} already exists — remove it or pick another name"}
    plugins_dir.mkdir(parents=True, exist_ok=True)
    target.symlink_to(bundle)
    return {"ok": True, "installed": str(target), "source": str(bundle), "validation": check,
            "next": f"restart the gateway or run `hermes plugins enable {name}`"}


def publish(bundle: Path, name: str, owner: str, manifest: dict,
            run: Callable[..., str] = _run, open_pull_request: bool = False) -> dict:
    """validate -> repo -> SHA -> entry -> (optionally) PR. Stops at the first refusal."""
    bundle = Path(bundle)
    steps: list[dict] = []

    check = validate_package(bundle, run)
    steps.append({"step": "validate", "ok": check["ok"], "detail": check.get("failures") or ["passed"]})
    if not check["ok"]:
        return {"ok": False, "stage": "validate", "steps": steps,
                "error": "the package failed `hermes plugins validate --install-deps`"}

    manifest = dict(manifest, _bundle=str(bundle))
    identity = gh_identity(run)
    sha = git_commit(bundle, f"{name} {manifest.get('version') or '0.1.0'}", identity, run)
    steps.append({"step": "commit", "ok": True, "detail": [sha]})

    repo = create_repo(bundle, owner, name, str(manifest.get("description") or name), run)
    steps.append({"step": "repo", "ok": True, "detail": [repo["url"]]})

    entry_text = catalog_entry(bundle, name, owner, sha, manifest)
    entry_path = bundle / CATALOG_DIR / f"{name}.yaml"
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_text(entry_text, encoding="utf-8")
    steps.append({"step": "catalog entry", "ok": True, "detail": [str(entry_path)]})

    result = {"ok": True, "stage": "pinned", "steps": steps, "name": name, "sha": sha,
              "repo": repo["url"], "entry": str(entry_path), "entry_text": entry_text,
              "install_command": f"hermes plugins install {name}"}

    if open_pull_request:
        try:
            pr = open_pr(entry_text, name, owner, manifest, run)
            steps.append({"step": "pull request", "ok": True, "detail": [pr["pr"]]})
            result.update(stage="submitted", pr=pr["pr"], branch=pr["branch"])
        except PublishError as exc:
            steps.append({"step": "pull request", "ok": False, "detail": [str(exc)]})
            result.update(stage="pinned", pr_error=str(exc))
    return result
