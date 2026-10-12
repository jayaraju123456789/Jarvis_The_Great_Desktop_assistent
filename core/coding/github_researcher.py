"""
core/coding/github_researcher.py — GitHub Research and Repository Intelligence for JARVIS.

Capabilities:
1. Search GitHub for open-source repositories matching application requirements.
2. Fallback to DuckDuckGo/Web scraping if GitHub API rate limit is reached or token is unavailable.
3. Compare multiple candidate repositories (activity, stars, license, dependencies).
4. Inspect repository directory structure, README, dependency manifests, and architectural patterns.
5. Strict repository safety: treats all external repo files as untrusted, static analysis only, never executes external scripts.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.logger import log_event


@dataclass
class RepoSummary:
    full_name: str
    html_url: str
    description: str
    stars: int
    forks: int
    language: str
    license_name: str
    updated_at: str
    topics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RepoDeepInspection:
    full_name: str
    html_url: str
    readme_snippet: str
    license_type: str
    manifest_files: List[str] = field(default_factory=list)
    top_level_structure: List[str] = field(default_factory=list)
    detected_patterns: List[str] = field(default_factory=list)
    security_notice: str = "Untrusted external repository: static inspection only. Execution prohibited."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GitHubResearcher:
    """Discovers, compares, and statically inspects GitHub repositories for engineering research."""

    def __init__(self):
        self.github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        # Check config/api_keys.json if present
        if not self.github_token:
            try:
                from core.config import get_config
                cfg = get_config()
                self.github_token = cfg.get("github_token")
            except Exception:
                pass

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "JARVIS-Autonomous-Coding-Agent/2.0",
            "Accept": "application/vnd.github.v3+json",
        }
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        return headers

    def search_repositories(
        self,
        query: str,
        language: Optional[str] = None,
        sort: str = "stars",
        max_results: int = 5,
    ) -> List[RepoSummary]:
        """
        Search GitHub for relevant software repositories matching keywords and language.
        Gracefully falls back to web search if API is unavailable or rate limited.
        """
        clean_q = query.strip()
        if language:
            clean_q += f" language:{language}"

        encoded_q = urllib.parse.quote(clean_q)
        url = f"https://api.github.com/search/repositories?q={encoded_q}&sort={sort}&order=desc&per_page={max_results}"

        results: List[RepoSummary] = []

        try:
            req = urllib.request.Request(url, headers=self._get_headers())
            with urllib.request.urlopen(req, timeout=12) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    items = data.get("items", [])
                    for item in items[:max_results]:
                        lic = item.get("license") or {}
                        lic_name = lic.get("name") or lic.get("spdx_id") or "Unspecified"
                        results.append(
                            RepoSummary(
                                full_name=item.get("full_name", ""),
                                html_url=item.get("html_url", ""),
                                description=item.get("description") or "No description provided.",
                                stars=item.get("stargazers_count", 0),
                                forks=item.get("forks_count", 0),
                                language=item.get("language") or "Mixed",
                                license_name=lic_name,
                                updated_at=item.get("updated_at", ""),
                                topics=item.get("topics", []),
                            )
                        )
                    if results:
                        log_event("agent", f"GitHub API found {len(results)} repos for: {query}", "INFO", "RESEARCH", "GitHubResearcher")
                        return results
        except urllib.error.HTTPError as e:
            log_event("agent", f"GitHub API HTTP {e.code} ({e.reason}) — trying fallback search", "WARNING", "RESEARCH", "GitHubResearcher")
        except Exception as e:
            log_event("agent", f"GitHub API search error: {e} — trying fallback search", "WARNING", "RESEARCH", "GitHubResearcher")

        # Fallback: Web search via DuckDuckGo / web_search
        return self._search_via_web_fallback(query, language, max_results)

    def _search_via_web_fallback(
        self,
        query: str,
        language: Optional[str] = None,
        max_results: int = 3,
    ) -> List[RepoSummary]:
        """DuckDuckGo fallback when GitHub API rate-limited or offline."""
        try:
            from actions.web_search import _ddg_search
            ddg_query = f"site:github.com {query}"
            if language:
                ddg_query += f" {language}"

            ddg_hits = _ddg_search(ddg_query, max_results=max_results + 2)
            results = []
            for hit in ddg_hits:
                href = hit.get("href", "")
                title = hit.get("title", "")
                snippet = hit.get("body", "")

                # Extract github repo name
                m = re.search(r"github\.com/([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+)", href)
                if m:
                    full_name = m.group(1).rstrip("/")
                    results.append(
                        RepoSummary(
                            full_name=full_name,
                            html_url=f"https://github.com/{full_name}",
                            description=snippet[:200] if snippet else title,
                            stars=0,
                            forks=0,
                            language=language or "Discovered via Search",
                            license_name="Check Repo",
                            updated_at="Recent",
                            topics=[],
                        )
                    )
                if len(results) >= max_results:
                    break
            return results
        except Exception as e:
            log_event("agent", f"Fallback repo search failed: {e}", "WARNING", "RESEARCH", "GitHubResearcher")
            return []

    def inspect_repository(self, full_name: str) -> RepoDeepInspection:
        """
        Statically inspect repository structure, README, and dependency manifests via GitHub API.
        Enforces read-only safety: never downloads executable binaries or runs code.
        """
        readme_snippet = ""
        manifests = []
        structure = []
        license_type = "Unknown"
        patterns = []

        # 1. Fetch README
        try:
            readme_url = f"https://api.github.com/repos/{full_name}/readme"
            req = urllib.request.Request(readme_url, headers=self._get_headers())
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    # Download raw content
                    raw_url = data.get("download_url")
                    if raw_url:
                        with urllib.request.urlopen(raw_url, timeout=10) as raw_resp:
                            raw_text = raw_resp.read().decode("utf-8", errors="ignore")
                            readme_snippet = raw_text[:800]
        except Exception:
            readme_snippet = "README not directly accessible."

        # 2. Fetch root tree contents
        try:
            contents_url = f"https://api.github.com/repos/{full_name}/contents"
            req = urllib.request.Request(contents_url, headers=self._get_headers())
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    items = json.loads(resp.read().decode("utf-8"))
                    for item in items:
                        name = item.get("name", "")
                        structure.append(f"{name} ({item.get('type')})")
                        if name.lower() in ("requirements.txt", "package.json", "pyproject.toml", "pom.xml", "dockerfile"):
                            manifests.append(name)
                        if name.lower() in ("license", "license.md", "license.txt"):
                            license_type = "Verified License File Found"
        except Exception:
            pass

        # Identify architectural patterns from names
        struct_str = " ".join(structure).lower()
        if "src" in struct_str:
            patterns.append("Standard src/ layout")
        if "tests" in struct_str or "test" in struct_str:
            patterns.append("Automated test suite present")
        if "dockerfile" in struct_str or "docker-compose" in struct_str:
            patterns.append("Containerized environment")
        if "api" in struct_str or "routes" in struct_str:
            patterns.append("Modular API routing architecture")

        return RepoDeepInspection(
            full_name=full_name,
            html_url=f"https://github.com/{full_name}",
            readme_snippet=readme_snippet,
            license_type=license_type,
            manifest_files=manifests,
            top_level_structure=structure[:15],
            detected_patterns=patterns,
        )

    def compare_repositories(
        self,
        repositories: List[RepoSummary],
        user_requirements: str,
    ) -> Dict[str, Any]:
        """
        Compare candidate repositories and rank suitability for the user's requirements.
        """
        if not repositories:
            return {"recommended": None, "comparison": "No candidate repositories provided."}

        scored = []
        req_lower = user_requirements.lower()

        for repo in repositories:
            score = 0
            # Stars factor
            score += min(repo.stars / 100, 20)
            # Language match
            if repo.language.lower() in req_lower:
                score += 25
            # Keyword match in description
            desc_words = repo.description.lower().split()
            matching_words = [w for w in desc_words if len(w) > 3 and w in req_lower]
            score += len(matching_words) * 5
            # Permissive license bonus
            if any(l in repo.license_name.lower() for l in ("mit", "apache", "bsd")):
                score += 15

            scored.append({
                "repo": repo.full_name,
                "url": repo.html_url,
                "score": round(score, 1),
                "language": repo.language,
                "license": repo.license_name,
                "stars": repo.stars,
                "description": repo.description,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        return {
            "recommended": scored[0]["repo"] if scored else None,
            "top_candidate": scored[0] if scored else None,
            "all_candidates": scored,
        }


# Global instance
github_researcher = GitHubResearcher()
