"""
Live contract tests against the NHL API.

Every test here calls the real endpoints. They exist to catch the NHL changing a
payload under us, not to test our logic in isolation.

The run is tagged with the current season phase, because the API behaves
differently depending on it -- the preseason in particular is when the NHL
experiments on its side. The phase is shown in the pytest header and summary,
and, when set, written to:

    NHL_API_REPORT   path of a Markdown report (used by CI for issues/summaries)
    GITHUB_OUTPUT    `season_state=<phase>` for later workflow steps

Set NHL_API_FORCE_SEASON_STATE (e.g. preseason) to run as if in that phase.
"""

import os
from datetime import date

import pytest

from nhl_api_redux.seasons import get_season_state

PRESEASON_WARNING = (
    "The NHL preseason is under way. The API is unstable in this period and the "
    "NHL tests changes on its side, so failures may be temporary."
)


def _load_season_state():
    try:
        return get_season_state()
    except Exception as e:  # The seasons endpoint itself is under test; never abort collection.
        return {"state": "unknown", "season": None, "error": str(e)}


SEASON = _load_season_state()
if os.environ.get("NHL_API_FORCE_SEASON_STATE"):
    SEASON["state"] = os.environ["NHL_API_FORCE_SEASON_STATE"]


def describe_season(season=SEASON):
    if season["state"] == "unknown":
        return f"season state unknown ({season.get('error')})"
    text = f"season {season['season']}: {season['state']}"
    if season.get("days_until_season") is not None:
        text += f", {season['days_until_season']} days until the season starts"
    if season.get("preseason_start"):
        text += f" (preseason {season['preseason_start']}, opening night {season['season_start']})"
    return text


def check_keys(payload, *paths, where="payload"):
    """
    Assert that each dotted path (e.g. "awayTeam.name.default") exists in payload.
    Reports every missing path at once, so one run shows the whole change.
    """
    missing = []
    for path in paths:
        node = payload
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                missing.append(path)
                break
            node = node[key]
    assert not missing, f"{where} is missing {missing}; present keys: {sorted(payload)}"


@pytest.fixture(scope="session")
def season_state():
    return SEASON


def pytest_report_header(config):
    lines = [f"NHL {describe_season()}"]
    if SEASON["state"] == "preseason":
        lines.append(f"PRESEASON: {PRESEASON_WARNING}")
    return lines


def pytest_collection_modifyitems(config, items):
    if SEASON["state"] == "preseason":
        return
    skip = pytest.mark.skip(reason=f"not in preseason ({describe_season()})")
    for item in items:
        if "live_preseason" in item.keywords:
            item.add_marker(skip)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    terminalreporter.section("NHL season")
    terminalreporter.write_line(describe_season())
    if SEASON["state"] == "preseason":
        terminalreporter.write_line(f"PRESEASON: {PRESEASON_WARNING}", yellow=True, bold=True)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"season_state={SEASON['state']}\n")

    report_path = os.environ.get("NHL_API_REPORT")
    if report_path:
        _write_report(report_path, terminalreporter.stats)


def _write_report(path, stats):
    counts = {k: len(stats.get(k, [])) for k in ("passed", "failed", "error", "skipped", "rerun")}
    lines = [f"## NHL API contract check — {date.today().isoformat()}", ""]
    if SEASON["state"] == "preseason":
        lines += [f"> [!WARNING]", f"> **Preseason run.** {PRESEASON_WARNING}", ""]
    lines += [
        f"**NHL {describe_season()}**",
        "",
        " · ".join(f"{name}: {n}" for name, n in counts.items()),
        "",
    ]
    problems = stats.get("failed", []) + stats.get("error", [])
    if problems:
        lines += ["### Failures", ""]
        for report in problems:
            # The assertion message names what changed (missing keys, new teams...).
            crash = getattr(report.longrepr, "reprcrash", None)
            excerpt = crash.message if crash else "\n".join(report.longreprtext.strip().splitlines()[-15:])
            lines += [f"<details><summary><code>{report.nodeid}</code></summary>", "", "```", excerpt, "```", "</details>", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
