#!/usr/bin/env python3
"""Collect GitHub numbers for the profile card and write cache/stats.json.

Needs a token in ACCESS_TOKEN. The workflow's own GITHUB_TOKEN sees public
repositories only; a personal access token also counts private ones.
Lines of code are summed commit by commit, so per-repository totals are kept
in cache/loc.json and only repositories whose head moved are counted again.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
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
        entry = cache.get(name)
        if not entry or entry["oid"] != oid:
            try:
                add, rem = count_lines(name, user["id"]) if commits else (0, 0)
                entry = {"oid": oid, "commits": commits, "additions": add, "deletions": rem}
                print(f"counted {name}: {commits} commits, +{add} -{rem}")
            except RuntimeError as e:
                print(f"skipped {name}: {e}", file=sys.stderr)
                if not entry:
                    continue
        fresh[name] = entry

    stats = {
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
    (ROOT / "cache" / "stats.json").write_text(json.dumps(stats, indent=1) + "\n")
    print(stats)


if __name__ == "__main__":
    main()
