"""Static BitSight payloads replayed during offline selftests.

The JSON fixtures below are direct copies of the BitSight API responses shared
in the runbook for healthcheck coverage:

* `name` – `GET /companies/search?name=GitHub`
* `domain` – `GET /companies/search?domain=github.com`
* `random` – empty search response for a non-existent company

We keep them verbatim (links/count/results) so that offline diagnostics can
exercise the exact payloads from production without depending on network I/O.
"""

COMPANY_SEARCH_SAMPLE_PAYLOADS: dict[str, dict] = {
    "name": {
        "links": {
            "next": None,
            "previous": None,
        },
        "count": 5,
        "results": [
            {
                "guid": "6ca077e2-b5a7-42c2-ae1e-a974c3a91dc1",
                "name": "GitHub Company",
                "industry": "Technology",
                "industry_slug": "technology",
                "primary_domain": "github.com",  # NOSONAR
                "description": (
                    "GitHub Company holds the companies that form the collective, "
                    "including npm, Inc. and GitHub, Inc. The company is "
                    "headquartered in San Francisco, California."
                ),
                "website": "http://www.github.com",  # NOSONAR
            },
            {
                "guid": "e90b389b-0b7e-4722-9411-97d81c8e2bc6",
                "name": "GitHub, Inc.",
                "industry": "Technology",
                "industry_slug": "technology",
                "primary_domain": "github.com",
                "description": (
                    "GitHub, Inc. provides an artificial intelligence-powered "
                    "developer platform to build, scale, and deliver secure "
                    "software. The company was founded in 2008 and is "
                    "headquartered in San Francisco, California."
                ),
                "website": "http://www.github.com",  # NOSONAR
            },
            {
                "guid": "a3b69f2e-ec1b-491e-adc9-e228cbd964a8",
                "name": "GitHub Blog",
                "industry": "Technology",
                "industry_slug": "technology",
                "primary_domain": "github.blog",
                "description": (
                    "GitHub Blog provides information on GitHub repositories. The "
                    "company is headquartered in San Francisco, California."
                ),
                "website": "http://www.atom.io",  # NOSONAR
            },
            {
                "guid": "fc5b5fed-6d74-479d-8257-29439e635a71",
                "name": "Github Notion Synch",
                "industry": "Technology",
                "industry_slug": "technology",
                "primary_domain": "githubnotionsync.com",
                "description": (
                    "Github Notion Synch provides a tool for synchronizing GitHub "
                    "issues and labels. The company is headquartered in "
                    "Mochengladbach, Germany."
                ),
                "website": "http://githubnotionsync.com",  # NOSONAR
            },
            {
                "guid": "b6e60e88-dd18-447b-afe7-0951ba952b87",
                "name": "WinAuth",
                "industry": "Technology",
                "industry_slug": "technology",
                "primary_domain": "winauth.github.io",
                "description": "WinAuth is a portable open-source authenticator for Windows.",
                "website": "http://winauth.github.io",  # NOSONAR
            },
        ],
    },
    "domain": {
        "links": {
            "next": None,
            "previous": None,
        },
        "count": 3,
        "results": [
            {
                "guid": "6ca077e2-b5a7-42c2-ae1e-a974c3a91dc1",
                "name": "GitHub Company",
                "industry": "Technology",
                "industry_slug": "technology",
                "primary_domain": "github.com",
                "description": (
                    "GitHub Company holds the companies that form the collective, "
                    "including npm, Inc. and GitHub, Inc. The company is "
                    "headquartered in San Francisco, California."
                ),
                "website": "http://www.github.com",  # NOSONAR
            },
            {
                "guid": "e90b389b-0b7e-4722-9411-97d81c8e2bc6",
                "name": "GitHub, Inc.",
                "industry": "Technology",
                "industry_slug": "technology",
                "primary_domain": "github.com",
                "description": (
                    "GitHub, Inc. provides an artificial intelligence-powered "
                    "developer platform to build, scale, and deliver secure "
                    "software. The company was founded in 2008 and is "
                    "headquartered in San Francisco, California."
                ),
                "website": "http://www.github.com",  # NOSONAR
            },
            {
                "guid": "5ebe8c20-0235-4300-82cb-2e0d6a5174af",
                "name": "Microsoft Group of Companies",
                "industry": "Technology",
                "industry_slug": "technology",
                "primary_domain": "microsoft.com",
                "description": (
                    "Microsoft Group of Companies holds the companies that form the "
                    "collective, including Activision Blizzard Corporation, GitHub "
                    "Company, LinkedIn Group of Companies, and Microsoft "
                    "Corporation. The group is headquartered in Redmond, Washington."
                ),
                "website": "http://www.microsoft.com",  # NOSONAR
            },
        ],
    },
    "random": {
        "links": {
            "next": None,
            "previous": None,
        },
        "count": 0,
        "results": [],
    },
}


__all__ = ["COMPANY_SEARCH_SAMPLE_PAYLOADS"]
