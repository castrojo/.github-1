#!/usr/bin/env bash
# transient-errors.sh — classify a failed git push as transient (retryable) or
# fatal (fail fast).
#
# Sourced by callers. Pure: classify_push_error() echoes a category string and
# performs no I/O, so it is unit-testable. The retry loop in
# git-push-retry.sh sources this file and uses is_transient_error() to decide
# whether to back off and retry or abort.
#
# Why classification matters: a rejected push is not always a race. An auth
# failure will fail identically on every attempt, so retrying it only wastes
# time and masks a real credential problem (tuna-os/.github#108). Only races
# and transport errors are worth retrying; everything else fails fast.

# classify_push_error <exit_code> <stderr_text>
#   exit_code   the non-zero exit status returned by the failed command
#   stderr_text the command's combined stderr (may be empty)
# Echoes exactly one of: race | network | auth | fatal
#   race      non-fast-forward / "updates were rejected" — a concurrent writer
#             won the race; the working copy is stale, so re-clone and retry.
#   network   transport / timeout / TLS / DNS failure — transient; retry after
#             backoff.
#   auth      authentication or authorization failure — fatal; do not retry.
#   fatal     anything else — unknown is not retryable, so fail fast rather than
#             burn every attempt on a non-transient error.
classify_push_error() {
  local code="$1"
  local msg="${2-}"
  local lower

  lower="$(printf '%s' "$msg" | tr '[:upper:]' '[:lower:]')"

  # No message to match on: fall back to the exit code. git (and most
  # transport tools) exit 128 on transport/fatal errors, treated here as
  # network (retryable) rather than assuming a fatal error.
  if [ -z "$lower" ]; then
    if [ "${code:-128}" = "128" ]; then
      echo "network"
    else
      echo "fatal"
    fi
    return
  fi

  case "$lower" in
    *non-fast-forward*|*"updates were rejected"*|*"because you have used force"*|*"failed to update ref"*)
      echo "race" ;;
    *"authentication required"*|*"permission denied"*|*"invalid username"*|*"bad credentials"*|*"access denied"*|*"could not authenticate"*|*"fatal: authentication failed"*)
      echo "auth" ;;
    *"could not read from remote repository"*|*"connection timed out"*|*"connection reset"*|*"rpc failed"*|*"transfer closed"*|*"unable to access"*|*"failed to resolve"*|*"no address"*|*"network is unreachable"*|*"tls handshake"*|*ssl*)
      echo "network" ;;
    *)
      echo "fatal" ;;
  esac
}

# is_transient_error <category>
# Return 0 (true) when the category from classify_push_error() is worth
# retrying, 1 (false) otherwise.
is_transient_error() {
  case "$1" in
    race|network) return 0 ;;
    *) return 1 ;;
  esac
}
