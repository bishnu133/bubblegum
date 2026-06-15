# Publishing to PyPI (Trusted Publishing)

Bubblegum publishes via **PyPI Trusted Publishing (OIDC)** — GitHub Actions
authenticates to PyPI with a short-lived OIDC token, so **no API tokens are
stored as repo secrets**. The workflow is `.github/workflows/publish.yml`.

| Trigger | What happens | Where |
| --- | --- | --- |
| Manual run (`workflow_dispatch`) | Build + verify, then upload | **TestPyPI** (dry run) |
| Push a `v*` tag | Build + verify, then upload | **PyPI** (real release) |

A normal merge to `main` never publishes — only a tag push does.

---

## One-time setup (maintainer)

You must register this repo as a **trusted publisher** on both TestPyPI and PyPI
*before* the first run. Because the project doesn't exist on PyPI yet, use the
**"pending publisher"** flow (PyPI lets you pre-authorize a publisher for a name
you haven't uploaded to yet).

### 1. TestPyPI (for the dry run)

1. Sign in at <https://test.pypi.org/> → **Account settings** → **Publishing**.
2. Under **Add a new pending publisher**, enter exactly:
   - **PyPI Project Name:** `bubblegum-ai`
   - **Owner:** `bishnu133`
   - **Repository name:** `bubblegum`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `testpypi`
3. Save.

### 2. PyPI (for the real release)

1. Sign in at <https://pypi.org/> → **Account settings** → **Publishing**.
2. **Add a new pending publisher** with exactly:
   - **PyPI Project Name:** `bubblegum-ai`
   - **Owner:** `bishnu133`
   - **Repository name:** `bubblegum`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. Save.

> The **Environment name** must match the `environment:` value in the workflow
> job (`testpypi` / `pypi`). GitHub auto-creates these environments on first use;
> optionally add protection rules (required reviewers) under
> **Repo → Settings → Environments** to gate real PyPI publishes behind an
> approval.

---

## Releasing

### Step A — Dry run to TestPyPI

1. **Repo → Actions → Publish → Run workflow** (on `main`).
2. Watch the `build` job (strict gates + `python -m build` + `twine check`) then
   the `testpypi` job upload.
3. Verify in a clean environment:
   ```bash
   python -m venv /tmp/bg && . /tmp/bg/bin/activate
   pip install -i https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple/ "bubblegum-ai==0.0.6a0"
   python -c "import bubblegum; print(bubblegum.__version__)"   # -> 0.0.6a0
   ```
   (The extra index lets `pydantic`/`pyyaml` resolve from real PyPI while the
   package itself comes from TestPyPI.)

### Step B — Real release to PyPI

1. Make sure `pyproject.toml` `version` is the version you intend to publish
   (`0.0.6a0`) and `main` is green.
2. Tag and push:
   ```bash
   git checkout main && git pull
   git tag v0.0.6-alpha
   git push origin v0.0.6-alpha
   ```
3. The tag push triggers the `pypi` job. Verify:
   ```bash
   pip install "bubblegum-ai==0.0.6a0"
   ```
4. Create the GitHub Release for `v0.0.6-alpha` (release notes from `CHANGELOG.md`).

> PyPI versions are **immutable** — you cannot re-upload `0.0.6a0` once published.
> If a build is wrong, bump to the next version (`0.0.6a1`) and re-tag.

---

## Re-running / troubleshooting

- **`non-existent or non-trusted publisher`** → the pending-publisher values
  don't match the workflow (owner/repo/workflow filename/environment). Re-check
  the table above; the environment name is the most common mismatch.
- **`File already exists`** on PyPI → that version was already published; bump the
  version and re-tag.
- TestPyPI runs are repeatable as long as the version string hasn't already been
  uploaded there; bump or delete the TestPyPI release to re-run the same version.

## Why Trusted Publishing (vs. an API token)

No long-lived secret to store, leak, or rotate; the OIDC token is minted
per-run and scoped to this repo + workflow + environment. This is PyPI's
recommended path and what the dual-publish plan in
`distribution-npm-and-pypi.md` standardizes on (the npm side will use npm's
equivalent OIDC provenance when we wire `0.2.0`).
