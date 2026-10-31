import re
from urllib.parse import urlparse

from app.core.exceptions import ValidationException

# GitHub owner and repository name rules
_GITHUB_REPO_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")


def validate_and_normalize_github_url(url: str) -> str:
    """Validate and normalize a public GitHub repository HTTPS URL.

    Rejects:
    - Non-HTTPS protocols
    - Non-github.com hostnames
    - Embedded user credentials (e.g. user:pass@)
    - Query strings or URL fragments
    - Path traversal or nested subpaths beyond <owner>/<repo>
    """
    if not url or not isinstance(url, str):
        raise ValidationException("Repository URL must be a non-empty string.")

    url = url.strip()

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValidationException(f"Invalid URL structure: {exc}") from exc

    if parsed.scheme.lower() != "https":
        raise ValidationException(
            f"Unsupported scheme '{parsed.scheme}'. Only public HTTPS repositories are supported."
        )

    if parsed.username or parsed.password:
        raise ValidationException(
            "Embedded credentials in repository URLs are strictly prohibited."
        )

    if parsed.hostname is None or parsed.hostname.lower() not in ("github.com", "www.github.com"):
        raise ValidationException(
            f"Unsupported host '{parsed.hostname}'. Only github.com is supported."
        )

    if parsed.port and parsed.port != 443:
        raise ValidationException("Non-standard ports are not allowed for GitHub repository URLs.")

    if parsed.query:
        raise ValidationException("Query parameters are not permitted in repository URLs.")

    if parsed.fragment:
        raise ValidationException("URL fragments are not permitted in repository URLs.")

    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]

    segments = [s for s in path.split("/") if s]
    if len(segments) != 2:
        raise ValidationException(
            "GitHub repository URL must point directly to '<owner>/<repo>' with no extra subpaths."
        )

    owner, repo = segments
    full_target = f"{owner}/{repo}"

    if not _GITHUB_REPO_PATTERN.match(full_target):
        raise ValidationException(
            f"Invalid repository path '{full_target}'. "
            "Owner and repo must contain only valid GitHub identifier characters."
        )

    if owner in (".", "..") or repo in (".", ".."):
        raise ValidationException("Path traversal segments are prohibited.")

    return f"https://github.com/{owner}/{repo}"
