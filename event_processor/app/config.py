"""All deployment-specific settings live here and come from the environment."""
import os


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://incidentmind:incidentmind@localhost:5433/incidentmind",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

DEAD_LETTER_TOPIC = os.getenv("DEAD_LETTER_TOPIC", "events-dead-letter")
MAX_PROCESSING_ATTEMPTS = int(os.getenv("MAX_PROCESSING_ATTEMPTS", "3"))

# Failure-rate detector. A 10-second window needs a minimum volume,
# otherwise 1 failure out of 2 payments would look like a 50% outage.
# The threshold is deliberately low: a complete outage at one bank with 20%
# of traffic moves the overall failure rate by only about 16 points.
FAILURE_RATE_THRESHOLD = float(os.getenv("FAILURE_RATE_THRESHOLD", "0.10"))
MIN_PAYMENT_ATTEMPTS = int(os.getenv("MIN_PAYMENT_ATTEMPTS", "10"))

# Evidence windows used by the investigator, in seconds.
INCIDENT_LOOKBACK_SECONDS = int(os.getenv("INCIDENT_LOOKBACK_SECONDS", "300"))
BASELINE_LOOKBACK_SECONDS = int(os.getenv("BASELINE_LOOKBACK_SECONDS", "3600"))
