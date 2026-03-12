"""Tests for the feedback-analysis recipe YAML."""

from __future__ import annotations

from pathlib import Path

import yaml
import pytest

RECIPE_PATH = (
    Path(__file__).resolve().parent.parent / "recipes" / "feedback-analysis.yaml"
)


@pytest.fixture
def recipe() -> dict:
    """Load and parse the recipe YAML."""
    assert RECIPE_PATH.exists(), f"Recipe file not found: {RECIPE_PATH}"
    text = RECIPE_PATH.read_text()
    data = yaml.safe_load(text)
    assert isinstance(data, dict), "Recipe YAML must parse to a dict"
    return data


# -- Metadata ----------------------------------------------------------------


def test_recipe_name(recipe: dict) -> None:
    assert recipe["name"] == "feedback-analysis"


def test_recipe_version(recipe: dict) -> None:
    assert recipe["version"] == "1.0.0"


def test_recipe_tags(recipe: dict) -> None:
    tags = recipe["tags"]
    assert isinstance(tags, list)
    assert "feedback" in tags
    assert "analysis" in tags
    assert "session" in tags


# -- Context variables -------------------------------------------------------


def test_context_has_session_id(recipe: dict) -> None:
    ctx = recipe["context"]
    assert "session_id" in ctx


def test_context_has_transcript_path(recipe: dict) -> None:
    ctx = recipe["context"]
    assert "transcript_path" in ctx


def test_context_has_daemon_session_path(recipe: dict) -> None:
    ctx = recipe["context"]
    assert "daemon_session_path" in ctx


def test_context_session_id_required(recipe: dict) -> None:
    """Required vars use empty string by convention."""
    assert recipe["context"]["session_id"] == ""


def test_context_transcript_path_required(recipe: dict) -> None:
    assert recipe["context"]["transcript_path"] == ""


def test_context_daemon_session_path_optional(recipe: dict) -> None:
    """Optional vars have a non-empty default or are explicitly empty-OK."""
    # daemon_session_path is optional; it may default to empty but the spec
    # says "optional" so we just confirm it exists (tested above).
    assert "daemon_session_path" in recipe["context"]


# -- Steps structure ---------------------------------------------------------


def test_recipe_has_two_steps(recipe: dict) -> None:
    assert "steps" in recipe
    assert len(recipe["steps"]) == 2


# -- Step 1: github-search --------------------------------------------------


def test_step1_id(recipe: dict) -> None:
    step = recipe["steps"][0]
    assert step["id"] == "github-search"


def test_step1_timeout(recipe: dict) -> None:
    step = recipe["steps"][0]
    assert step["timeout"] == 120


def test_step1_output(recipe: dict) -> None:
    step = recipe["steps"][0]
    assert step["output"] == "github_findings"


def test_step1_prompt_mentions_gh_issue_list(recipe: dict) -> None:
    step = recipe["steps"][0]
    assert "gh issue list" in step["prompt"]


# -- Step 2: log-analysis ---------------------------------------------------


def test_step2_id(recipe: dict) -> None:
    step = recipe["steps"][1]
    assert step["id"] == "log-analysis"


def test_step2_timeout(recipe: dict) -> None:
    step = recipe["steps"][1]
    assert step["timeout"] == 180


def test_step2_output(recipe: dict) -> None:
    step = recipe["steps"][1]
    assert step["output"] == "all_findings"


def test_step2_references_github_findings(recipe: dict) -> None:
    """Step 2 prompt must reference {{github_findings}} from step 1."""
    step = recipe["steps"][1]
    assert "{{github_findings}}" in step["prompt"]


# -- Validation command (acceptance criterion) --------------------------------


def test_validation_command(recipe: dict) -> None:
    """Mirrors the spec validation: name present, steps present, 2 steps."""
    assert "name" in recipe
    assert "steps" in recipe
    assert len(recipe["steps"]) == 2
