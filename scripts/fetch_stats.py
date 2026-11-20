#!/usr/bin/env python3
"""Collect GitHub numbers for the profile card and write cache/stats.json.

Needs a token in ACCESS_TOKEN. The workflow's own GITHUB_TOKEN sees public
repositories only; a personal access token also counts private ones.
Lines of code are summed commit by commit, so per-repository totals are kept
in cache/loc.json (keyed by a hash of the repository name, since the cache is
public) and only repositories whose head moved are counted again.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com/graphql"
TOKEN = os.environ.get("ACCESS_TOKEN", "")

USER_Q = """
query($login: String!) {
  user(login: $login) {
    id
    createdAt
    followers { totalCount }
    repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) { totalCount }
  }
}"""

REPOS_Q = """
query($login: String!, $id: ID!, $cursor: String) {
  user(login: $login) {
    repositories(first: 50, after: $cursor, ownerAffiliations: OWNER) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        stargazerCount
        defaultBranchRef { target { ... on Commit { oid history(author: {id: $id}) { totalCount } } } }
      }
    }
  }
}"""

CALENDAR_Q = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}"""

LAST_YEAR_Q = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { weekday contributionLevel } }
      }
    }
  }
}"""

LOC_Q = """
query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: 100, after: $cursor, author: {id: $id}) {
        pageInfo { hasNextPage endCursor }
        nodes { additions deletions }
      }
    } } }
  }
}"""


def gql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, body, {"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-card"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            if data.get("data") and not data.get("errors"):
                return data["data"]
            error = data.get("errors")
        except (urllib.error.URLError, TimeoutError) as e:
            error = e
        time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"GitHub API request failed: {error}")


def count_lines(repo, user_id):
    owner, name = repo.split("/")
    add = rem = 0
    cursor = None
    while True:
        target = gql(LOC_Q, owner=owner, name=name, id=user_id, cursor=cursor)["repository"]["defaultBranchRef"]["target"]
        history = target["history"]
        for commit in history["nodes"]:
            add += commit["additions"]
            rem += commit["deletions"]
        if not history["pageInfo"]["hasNextPage"]:
            return add, rem
        cursor = history["pageInfo"]["endCursor"]


def streaks(login, created_at):
    """Current and longest run of consecutive days with at least one contribution."""
    today = datetime.now(timezone.utc).date()
    days = {}
    for year in range(int(created_at[:4]), today.year + 1):  # the API serves one year at a time
        data = gql(CALENDAR_Q, login=login, **{"from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"})
        for week in data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                days[day["date"]] = day["contributionCount"]
    return streak_lengths(days, today.isoformat())


def streak_lengths(days, today):
    longest = run = 0
    for day in sorted(d for d in days if d <= today):
        run = run + 1 if days[day] else 0
        longest = max(longest, run)
        if day == today and not days[day]:
            run = before_today  # today is not over yet, so an empty today does not break the streak
        before_today = run
    return run, longest


LEVEL = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def last_year(login):
    """The calendar GitHub shows on the profile: weeks of 7 levels (0-4), None outside the range."""
    cal = gql(LAST_YEAR_Q, login=login)["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = []
    for week in cal["weeks"]:
        days = [None] * 7
        for day in week["contributionDays"]:
            days[day["weekday"]] = LEVEL.get(day["contributionLevel"], 0)
        weeks.append(days)
    return {"total": cal["totalContributions"], "weeks": weeks}


def main():
    if not TOKEN:
        sys.exit("ACCESS_TOKEN is not set")
    login = json.loads((ROOT / "config.json").read_text())["username"]
    cache_file = ROOT / "cache" / "loc.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}

    user = gql(USER_Q, login=login)["user"]
    repos, cursor = [], None
    while True:
        page = gql(REPOS_Q, login=login, id=user["id"], cursor=cursor)["user"]["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    fresh = {}
    for repo in repos:
        name, ref = repo["nameWithOwner"], repo["defaultBranchRef"]
        if not ref:  # empty repository
            continue
        oid, commits = ref["target"]["oid"], ref["target"]["history"]["totalCount"]
        # the cache is committed to a public repository, so never store repository names in it
        key = hashlib.sha256(name.encode()).hexdigest()[:16]
        entry = cache.get(key)
        if not entry or entry["oid"] != oid:
            try:
                add, rem = count_lines(name, user["id"]) if commits else (0, 0)
                entry = {"oid": oid, "commits": commits, "additions": add, "deletions": rem}
                print(f"counted {key}: {commits} commits, +{add} -{rem}")
            except RuntimeError as e:
                print(f"skipped {key}: {e}", file=sys.stderr)
                if not entry:
                    continue
        fresh[key] = entry

    current, longest = streaks(login, user["createdAt"])
    stats = {
        "streak": current,
        "longest_streak": longest,
        "created_at": user["createdAt"],
        "followers": user["followers"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "repos": page["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "commits": sum(e["commits"] for e in fresh.values()),
        "additions": sum(e["additions"] for e in fresh.values()),
        "deletions": sum(e["deletions"] for e in fresh.values()),
    }
    cache_file.parent.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(fresh, indent=1, sort_keys=True) + "\n")
    (ROOT / "cache" / "calendar.json").write_text(json.dumps(last_year(login), separators=(",", ":")) + "\n")
    (ROOT / "cache" / "stats.json").write_text(json.dumps(stats, indent=1) + "\n")
    print(stats)


if __name__ == "__main__":
    main()
