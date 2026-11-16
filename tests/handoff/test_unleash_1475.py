# ABOUTME: Checks through the GitHub API that the commit fixing #19 is published here and named on
# ABOUTME: Unleash_an_Agent_Watch_It_Burn#1475, which moves its images/llm-guard submodule pointer to it.
import json
import os
import re
import urllib.request

API = "https://api.github.com"
THIS_REPO = "peopleforrester/llm-guard-cpu-offline"
CONSUMER_ISSUE = "peopleforrester/Unleash_an_Agent_Watch_It_Burn/issues/1475"
# The commit that moved the OpenTelemetry overrides to 1.45.2 and closes #19.
FIX_COMMIT = "ea3cad36ee152d424ace9140527d3c9db75b80a2"


def get(path: str):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    # The public API needs no token; CI passes its own to stay clear of the shared anonymous rate limit.
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(API + path, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def names_commit(text: str, sha: str) -> bool:
    """True when text carries sha, or a prefix of it at least 7 characters long, as a whole word."""
    return any(
        sha.startswith(word.lower())
        for word in re.findall(r"\b[0-9a-fA-F]{7,40}\b", text or "")
    )


def test_names_commit_matches_full_and_short_shas_only_as_words():
    assert names_commit(f"Moved the pointer to {FIX_COMMIT}.", FIX_COMMIT)
    assert names_commit(f"llm-guard-cpu-offline@{FIX_COMMIT[:7].upper()}", FIX_COMMIT)
    assert not names_commit(FIX_COMMIT[:6], FIX_COMMIT)
    assert not names_commit("68c450549b48cad63a3c8e41265df92460e4b050", FIX_COMMIT)
    assert not names_commit("x" + FIX_COMMIT[:12], FIX_COMMIT)


def test_fix_commit_is_published_and_closes_19():
    commit = get(f"/repos/{THIS_REPO}/commits/{FIX_COMMIT}")
    assert commit["sha"] == FIX_COMMIT
    assert re.search(r"^Closes #19$", commit["commit"]["message"], re.MULTILINE), commit["commit"][
        "message"
    ]


def test_fix_commit_is_named_on_unleash_1475():
    issue = get(f"/repos/{CONSUMER_ISSUE}")
    texts = [issue["body"]]
    page = 1
    while True:
        comments = get(f"/repos/{CONSUMER_ISSUE}/comments?per_page=100&page={page}")
        texts += [comment["body"] for comment in comments]
        if len(comments) < 100:
            break
        page += 1
    assert any(names_commit(text, FIX_COMMIT) for text in texts), (
        f"No body or comment of {issue['html_url']} names {FIX_COMMIT}, so the "
        "images/llm-guard submodule pointer there has no commit to move to"
    )
