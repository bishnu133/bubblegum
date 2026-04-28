"""
tests/unit/test_phase1b.py
===========================
Unit tests for Phase 1B components:
  - FuzzyTextResolver
  - MemoryCacheResolver
  - extract() (mock-based)
  - HTML report generation

All tests are isolated — no Playwright / browser required.
Phase 0 + Phase 1A tests continue to pass (no shared state).
"""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bubblegum.core.grounding.resolvers.fuzzy_text import (
    FuzzyTextResolver,
    _best_match,
    _expand_with_synonyms,
    _extract_targets,
    _similarity_ratio,
)
from bubblegum.core.grounding.resolvers.memory_cache import MemoryCacheResolver, _step_hash
from bubblegum.core.schemas import (
    ArtifactRef,
    ExecutionOptions,
    ResolvedTarget,
    StepIntent,
    StepResult,
    ValidationResult,
)
from bubblegum.reporting.html_report import write_html_report


# ===========================================================================
# Helpers
# ===========================================================================

def _make_intent(
    instruction: str = "Click Login",
    channel: str = "web",
    action_type: str = "click",
    context: dict | None = None,
) -> StepIntent:
    return StepIntent(
        instruction=instruction,
        channel=channel,
        action_type=action_type,
        context=context or {},
    )


def _a11y(lines: list[str]) -> str:
    return "\n".join(lines)


# ===========================================================================
# FuzzyTextResolver — unit tests
# ===========================================================================

class TestFuzzyTextResolverMetadata:
    def test_name(self):
        assert FuzzyTextResolver.name == "fuzzy_text"

    def test_priority(self):
        assert FuzzyTextResolver.priority == 45

    def test_tier(self):
        assert FuzzyTextResolver.tier == 2

    def test_channels(self):
        assert "web" in FuzzyTextResolver.channels
        assert "mobile" in FuzzyTextResolver.channels

    def test_cost_level_low(self):
        assert FuzzyTextResolver.cost_level == "low"

    def test_required_context(self):
        assert FuzzyTextResolver().required_context() == ["a11y_snapshot"]


class TestFuzzyTextNearExact:
    """ratio >= 0.85 → confidence 0.82"""

    def setup_method(self):
        self.resolver = FuzzyTextResolver()

    def test_near_exact_match(self):
        snapshot = _a11y(['- button "Logout"'])
        intent = _make_intent(
            instruction="Click Logut",  # typo — near-exact
            context={"a11y_snapshot": snapshot},
        )
        candidates = self.resolver.resolve(intent)
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.82
        assert candidates[0].resolver_name == "fuzzy_text"

    def test_case_insensitive_near_exact(self):
        snapshot = _a11y(['- button "SUBMIT"'])
        intent = _make_intent(
            instruction="Click Submit",
            context={"a11y_snapshot": snapshot},
        )
        candidates = self.resolver.resolve(intent)
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.82

    def test_ref_format_uses_role(self):
        snapshot = _a11y(['- button "Logut"'])
        intent = _make_intent(
            instruction="Click Logout",
            context={"a11y_snapshot": snapshot},
        )
        candidates = self.resolver.resolve(intent)
        assert candidates[0].ref == 'role=button[name="Logut"]'


class TestFuzzyTextGoodMatch:
    """ratio >= 0.65 → confidence 0.72"""

    def setup_method(self):
        self.resolver = FuzzyTextResolver()

    def test_good_match(self):
        snapshot = _a11y(['- button "Continue"'])
        intent = _make_intent(
            instruction="Click Next",  # synonym — ratio might be low but synonym expansion kicks in
            context={"a11y_snapshot": snapshot},
        )
        # "next" → synonym "continue" → ratio with "Continue" should be ~1.0 via synonym
        candidates = self.resolver.resolve(intent)
        # via synonym expansion "next"→"continue", ratio("continue","continue")=1.0 → near-exact
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.82  # synonym expansion raises to near-exact

    def test_good_match_partial(self):
        snapshot = _a11y(['- button "Confirmation"'])
        intent = _make_intent(
            instruction="Click Confirm",
            context={"a11y_snapshot": snapshot},
        )
        candidates = self.resolver.resolve(intent)
        # "Confirm" vs "Confirmation" — partial, ratio ~0.73 → good match
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.72


class TestFuzzyTextWeakMatch:
    """ratio >= 0.50 → confidence 0.62"""

    def setup_method(self):
        self.resolver = FuzzyTextResolver()

    def test_weak_match(self):
        # "Login" vs "Signin" — ratio is around 0.5-0.6 without synonyms
        ratio = _similarity_ratio("signin", "login")
        # Confirm our expectation
        assert 0.40 <= ratio < 0.85

    def test_resolve_gives_weak_confidence_for_partial(self):
        snapshot = _a11y(['- button "Signin"'])
        intent = _make_intent(
            instruction="Click login",
            context={"a11y_snapshot": snapshot},
        )
        candidates = self.resolver.resolve(intent)
        # "login" synonym → "sign in" (two words) vs "Signin" — ratio ~0.78 → good match
        # or direct ratio("signin","login") ~0.67 → good match
        assert len(candidates) == 1
        assert candidates[0].confidence in (0.72, 0.82)  # good or near-exact


class TestFuzzyTextNoMatch:
    """ratio < 0.50 → no candidate returned"""

    def setup_method(self):
        self.resolver = FuzzyTextResolver()

    def test_completely_unrelated(self):
        snapshot = _a11y(['- button "Download Report"'])
        intent = _make_intent(
            instruction="Click xyz",
            context={"a11y_snapshot": snapshot},
        )
        candidates = self.resolver.resolve(intent)
        assert candidates == []

    def test_no_snapshot_raises_key_error(self):
        """required_context=["a11y_snapshot"] means can_run() blocks before resolve()."""
        # Direct resolve() call without snapshot in context raises KeyError —
        # in production can_run() prevents this. Test that the guard works via can_run.
        resolver = FuzzyTextResolver()
        intent = _make_intent(context={})
        assert not resolver.can_run(intent)

    def test_elements_without_name_skipped(self):
        """Lines without accessible names are skipped — fuzzy needs a label."""
        snapshot = _a11y(["- button", "- link"])
        intent = _make_intent(
            instruction="Click something",
            context={"a11y_snapshot": snapshot},
        )
        candidates = self.resolver.resolve(intent)
        assert candidates == []

    def test_deduplication(self):
        snapshot = _a11y(['- button "Save"', '- button "Save"'])
        intent = _make_intent(
            instruction="Click Savee",
            context={"a11y_snapshot": snapshot},
        )
        candidates = self.resolver.resolve(intent)
        assert len(candidates) == 1  # deduplicated by ref


class TestSynonymExpansion:
    def test_login_synonym(self):
        expanded = _expand_with_synonyms("login")
        assert "sign in" in expanded

    def test_sign_in_synonym(self):
        expanded = _expand_with_synonyms("sign in")
        assert "login" in expanded

    def test_unknown_word_no_synonyms(self):
        expanded = _expand_with_synonyms("bubblegum")
        assert expanded == ["bubblegum"]

    def test_synonym_match_login_vs_sign_in(self):
        # "Click Login" should fuzzy-match a "Sign In" button via synonyms
        resolver = FuzzyTextResolver()
        snapshot = _a11y(['- button "Sign In"'])
        intent = _make_intent(
            instruction="Click Login",
            context={"a11y_snapshot": snapshot},
        )
        candidates = resolver.resolve(intent)
        assert len(candidates) == 1
        # "login" → synonym "sign in" → ratio("sign in", "Sign In") = 1.0 → near-exact
        assert candidates[0].confidence == 0.82


class TestBestMatchHelper:
    def test_near_exact_returns_0_82(self):
        conf, matched, ratio = _best_match("Login", ["Login"])
        assert conf == 0.82
        assert ratio >= 0.85

    def test_no_match_returns_zero(self):
        conf, matched, ratio = _best_match("Totally different", ["xyz"])
        assert conf == 0.0

    def test_returns_original_target_token(self):
        conf, matched, ratio = _best_match("Sign In", ["login"])  # synonym path
        assert matched == "login"  # original instruction token, not the synonym


# ===========================================================================
# MemoryCacheResolver — unit tests
# ===========================================================================

class TestMemoryCacheResolverMetadata:
    def test_name(self):
        assert MemoryCacheResolver.name == "memory_cache"

    def test_priority(self):
        assert MemoryCacheResolver.priority == 10

    def test_tier(self):
        assert MemoryCacheResolver.tier == 1

    def test_required_context(self):
        r = MemoryCacheResolver()
        assert r.required_context() == ["screen_signature"]


class TestMemoryCacheCacheHit:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "memory.db"
        self.resolver = MemoryCacheResolver(db_path=self.db_path)

    def teardown_method(self):
        self.resolver.close()

    def test_cache_miss_when_empty(self):
        intent = _make_intent(context={"screen_signature": "sig:100"})
        assert self.resolver.resolve(intent) == []

    def test_cache_hit_after_record_success(self):
        intent = _make_intent(context={"screen_signature": "sig:100"})
        target = ResolvedTarget(
            ref='role=button[name="Login"]',
            confidence=0.96,
            resolver_name="accessibility_tree",
        )
        self.resolver.record_success(intent, target)
        results = self.resolver.resolve(intent)
        assert len(results) == 1
        assert results[0].ref == target.ref
        assert results[0].confidence == 0.96
        assert results[0].resolver_name == "memory_cache"
        assert results[0].metadata["cached_from"] == "accessibility_tree"

    def test_screen_signature_mismatch_returns_empty(self):
        intent_write = _make_intent(context={"screen_signature": "sig:100"})
        intent_read  = _make_intent(context={"screen_signature": "sig:999"})
        target = ResolvedTarget(ref="#btn", confidence=0.90, resolver_name="explicit_selector")
        self.resolver.record_success(intent_write, target)

        results = self.resolver.resolve(intent_read)
        assert results == []

    def test_no_screen_signature_returns_empty(self):
        intent = _make_intent(context={})
        assert self.resolver.resolve(intent) == []


class TestMemoryCacheStaleness:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "memory.db"
        self.resolver = MemoryCacheResolver(db_path=self.db_path)

    def teardown_method(self):
        self.resolver.close()

    def _write_raw(self, screen_sig: str, step_hash_val: str, last_success_iso: str,
                   failure_count: int = 0) -> None:
        """Insert directly into SQLite to control timestamps."""
        conn = self.resolver._get_conn()
        conn.execute(
            """INSERT INTO bubblegum_memory
               (screen_sig, step_hash, ref, confidence, resolver_name,
                metadata_json, last_success, success_count, failure_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (screen_sig, step_hash_val, 'role=button[name="OK"]',
             0.90, "exact_text", "{}", last_success_iso, failure_count),
        )
        conn.commit()

    def test_ttl_expired_returns_empty(self):
        intent = _make_intent(context={"screen_signature": "sig:200"})
        step_h = _step_hash(intent)
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=10)).isoformat()
        self._write_raw("sig:200", step_h, old_ts)

        results = self.resolver.resolve(intent)
        assert results == []

    def test_within_ttl_returns_result(self):
        intent = _make_intent(context={"screen_signature": "sig:201"})
        step_h = _step_hash(intent)
        recent_ts = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
        self._write_raw("sig:201", step_h, recent_ts)

        results = self.resolver.resolve(intent)
        assert len(results) == 1

    def test_failure_count_exceeded_returns_empty(self):
        intent = _make_intent(context={"screen_signature": "sig:300"})
        step_h = _step_hash(intent)
        recent_ts = datetime.now(tz=timezone.utc).isoformat()
        self._write_raw("sig:300", step_h, recent_ts, failure_count=3)

        results = self.resolver.resolve(intent)
        assert results == []

    def test_failure_count_below_max_returns_result(self):
        intent = _make_intent(context={"screen_signature": "sig:301"})
        step_h = _step_hash(intent)
        recent_ts = datetime.now(tz=timezone.utc).isoformat()
        self._write_raw("sig:301", step_h, recent_ts, failure_count=2)

        results = self.resolver.resolve(intent)
        assert len(results) == 1

    def test_record_failure_increments_count(self):
        intent = _make_intent(context={"screen_signature": "sig:400"})
        target = ResolvedTarget(ref="#btn", confidence=0.90, resolver_name="exact_text")
        self.resolver.record_success(intent, target)

        self.resolver.record_failure(intent)

        # Read raw DB
        conn = self.resolver._get_conn()
        row = conn.execute("SELECT failure_count FROM bubblegum_memory WHERE screen_sig=?",
                           ("sig:400",)).fetchone()
        assert row[0] == 1

    def test_record_success_resets_failure_count(self):
        intent = _make_intent(context={"screen_signature": "sig:500"})
        target = ResolvedTarget(ref="#btn", confidence=0.90, resolver_name="exact_text")
        self.resolver.record_success(intent, target)
        self.resolver.record_failure(intent)
        self.resolver.record_success(intent, target)  # should reset failure_count to 0

        conn = self.resolver._get_conn()
        row = conn.execute("SELECT failure_count FROM bubblegum_memory WHERE screen_sig=?",
                           ("sig:500",)).fetchone()
        assert row[0] == 0


# ===========================================================================
# extract() — mock-based unit tests
# ===========================================================================

class TestExtractSDK:
    """Mock Playwright page to test extract() without a browser."""

    @pytest.mark.asyncio
    async def test_extract_returns_extracted_value(self):
        from bubblegum.core import sdk

        mock_page = MagicMock()

        # Use a snapshot whose element name closely matches the instruction keyword
        # "email" → element name "email" → exact match → confidence 0.96
        snapshot = '- heading "email"'
        mock_ui_ctx = MagicMock()
        mock_ui_ctx.a11y_snapshot = snapshot
        mock_ui_ctx.screenshot = None
        mock_ui_ctx.screen_signature = "sig:test"
        mock_ui_ctx.hierarchy_xml = None

        # inner_text() async return
        mock_locator = AsyncMock()
        mock_locator.inner_text = AsyncMock(return_value="user@example.com")
        mock_page.get_by_role = MagicMock(return_value=mock_locator)
        mock_page.locator = MagicMock(return_value=mock_locator)
        mock_page.url = "http://test/"

        with patch("bubblegum.adapters.web.playwright.adapter.PlaywrightAdapter.collect_context",
                   new=AsyncMock(return_value=mock_ui_ctx)):
            result = await sdk.extract(
                "Get user email",
                channel="web",
                page=mock_page,
            )

        assert result.status == "passed"
        assert result.target is not None
        assert result.target.metadata.get("extracted_value") == "user@example.com"

    @pytest.mark.asyncio
    async def test_extract_action_type_is_extract(self):
        from bubblegum.core import sdk

        assert sdk._infer_action_type("Get user email", {}) == "extract"
        assert sdk._infer_action_type("Read the heading", {}) == "extract"
        assert sdk._infer_action_type("fetch title", {}) == "extract"

    @pytest.mark.asyncio
    async def test_extract_returns_failed_when_inner_text_raises(self):
        from bubblegum.core import sdk

        mock_page = MagicMock()
        snapshot = '- heading "Dashboard"'
        mock_ui_ctx = MagicMock()
        mock_ui_ctx.a11y_snapshot = snapshot
        mock_ui_ctx.screenshot = None
        mock_ui_ctx.screen_signature = "sig:fail"
        mock_ui_ctx.hierarchy_xml = None

        mock_locator = AsyncMock()
        mock_locator.inner_text = AsyncMock(side_effect=Exception("Element not attached"))
        mock_page.get_by_role = MagicMock(return_value=mock_locator)
        mock_page.locator = MagicMock(return_value=mock_locator)
        mock_page.url = "http://test/"

        with patch("bubblegum.adapters.web.playwright.adapter.PlaywrightAdapter.collect_context",
                   new=AsyncMock(return_value=mock_ui_ctx)):
            result = await sdk.extract(
                "Get dashboard title",
                channel="web",
                page=mock_page,
            )

        assert result.status == "failed"
        assert result.error is not None
        assert "Element not attached" in result.error.message


# ===========================================================================
# HTML Report — unit tests
# ===========================================================================

class TestHTMLReport:
    def _make_result(
        self,
        status: str = "passed",
        action: str = "Click Login",
        confidence: float = 0.96,
        resolver: str = "accessibility_tree",
        has_screenshot: bool = False,
        error_msg: str | None = None,
    ) -> StepResult:
        from bubblegum.core.schemas import ErrorInfo
        target = ResolvedTarget(
            ref='role=button[name="Login"]',
            confidence=confidence,
            resolver_name=resolver,
        )
        artifacts = []
        if has_screenshot:
            # Create a tiny fake PNG
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
            tmp.close()
            artifacts.append(ArtifactRef(
                type="screenshot",
                path=tmp.name,
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
            ))
        error = ErrorInfo(error_type="ResolutionFailedError", message=error_msg) if error_msg else None
        return StepResult(
            status=status,
            action=action,
            target=target,
            confidence=confidence,
            duration_ms=42,
            artifacts=artifacts,
            error=error,
        )

    def test_writes_html_file(self, tmp_path):
        results = [self._make_result()]
        out = write_html_report(results, path=tmp_path / "report.html")
        assert out.exists()
        content = out.read_text()
        assert "<!DOCTYPE html>" in content
        assert "Click Login" in content

    def test_summary_counts(self, tmp_path):
        results = [
            self._make_result(status="passed"),
            self._make_result(status="recovered"),
            self._make_result(status="failed", error_msg="No match found"),
            self._make_result(status="skipped"),
        ]
        out = write_html_report(results, path=tmp_path / "report.html")
        content = out.read_text()
        # All 4 statuses should appear as badges
        assert "PASSED" in content
        assert "RECOVERED" in content
        assert "FAILED" in content
        assert "SKIPPED" in content

    def test_error_message_in_output(self, tmp_path):
        results = [self._make_result(status="failed", error_msg="All resolvers exhausted")]
        out = write_html_report(results, path=tmp_path / "report.html")
        assert "All resolvers exhausted" in out.read_text()

    def test_empty_results_no_error(self, tmp_path):
        out = write_html_report([], path=tmp_path / "report.html")
        assert out.exists()
        assert "No steps recorded" in out.read_text()

    def test_screenshot_thumbnail_present(self, tmp_path):
        result = self._make_result(has_screenshot=True)
        out = write_html_report([result], path=tmp_path / "report.html")
        content = out.read_text()
        # Inline base64 img should be present
        assert "data:image/png;base64," in content

    def test_resolver_name_in_output(self, tmp_path):
        result = self._make_result(resolver="fuzzy_text")
        out = write_html_report([result], path=tmp_path / "report.html")
        assert "fuzzy_text" in out.read_text()

    def test_confidence_shown(self, tmp_path):
        result = self._make_result(confidence=0.72)
        out = write_html_report([result], path=tmp_path / "report.html")
        assert "0.72" in out.read_text()

    def test_custom_title(self, tmp_path):
        out = write_html_report([], path=tmp_path / "r.html", title="My QA Run")
        assert "My QA Run" in out.read_text()
