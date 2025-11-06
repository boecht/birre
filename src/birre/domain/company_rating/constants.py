"""Constants for company rating and findings processing."""

# Severity category ranking values
SEVERITY_RANK_SEVERE = 3
SEVERITY_RANK_MATERIAL = 2
SEVERITY_RANK_MODERATE = 1
SEVERITY_RANK_LOW = 0
SEVERITY_RANK_UNKNOWN = -1

# Severity category names (lowercase for comparison)
SEVERITY_SEVERE = "severe"
SEVERITY_MATERIAL = "material"
SEVERITY_MODERATE = "moderate"
SEVERITY_LOW = "low"

# Default severity thresholds
DEFAULT_SEVERITY_FLOOR = SEVERITY_MODERATE

# Numeric severity scores (when severity is unknown/invalid)
SEVERITY_SCORE_UNKNOWN = -1.0

# Timestamp parsing
TIMESTAMP_INVALID = (
    0  # Epoch start (1970-01-01) used as sentinel for invalid/missing timestamps
)

# Findings processing limits
DEFAULT_FINDINGS_LIMIT = 1
DEFAULT_LOG_TAIL_LINES = 100
