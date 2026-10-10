#!/usr/bin/env bash
# backoff.sh — jittered exponential backoff for retry loops.
#
# Sourced by callers that retry a flaky operation (a git push that loses a
# race against a concurrent writer, an API call, a network fetch). Pure:
# backoff_interval() computes and echoes the number of seconds to wait without
# sleeping or doing any I/O, so it is unit-testable; backoff_sleep() wraps it
# with an actual sleep.
#
# Model: "full jitter" (AWS, 5 Tips for Building Resilient Systems, tip 4).
# The base delay grows exponentially per attempt and is capped; a random offset
# in [0, base] is then added so that many retrying callers desynchronize and
# stop colliding with one another instead of backing off in lockstep.

# backoff_interval <attempt> [base_seconds] [max_seconds] [factor]
#   attempt       1-based retry attempt number (1 = first retry)
#   base_seconds  base delay in seconds (default 1)
#   max_seconds   cap on the exponential term before jitter is added (default 30)
#   factor        multiplier applied per attempt (default 2)
# Echoes the integer number of seconds to wait.
backoff_interval() {
  local attempt="$1"
  local base="${2:-1}"
  local max="${3:-30}"
  local factor="${4:-2}"
  local term="$base"
  local i

  # term = base * factor^(attempt-1), capped at max. A loop (not a power)
  # keeps the arithmetic in integers and avoids `**` portability surprises.
  for (( i = 1; i < attempt; i++ )); do
    term=$(( term * factor ))
    (( term >= max )) && { term="$max"; break; }
  done

  # Full jitter: a random offset in [0, term].
  echo "$(( term + RANDOM % (term + 1) ))"
}

# backoff_sleep <attempt> [base_seconds] [max_seconds] [factor]
# Sleep for backoff_interval("$@").
backoff_sleep() {
  sleep "$(backoff_interval "$@")"
}
