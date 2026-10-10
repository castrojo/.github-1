#!/usr/bin/env bash
# Unit tests for the retry shell library in this directory.
#
# Runs with plain bash (no test framework): `bash .github/lib/test-shell-lib.sh`.
# Exits 0 when every assertion passes, 1 otherwise. The functions under test
# are pure (they echo / return), so these run fast and offline -- no network,
# no git, no token -- which is the point of the extraction: the retry logic is
# now independently testable instead of surfacing only during a publish.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/backoff.sh"
# shellcheck disable=SC1091
source "$HERE/transient-errors.sh"

failures=0
checks=0

# assert_eq <expected> <actual> <label>
assert_eq() {
  checks=$(( checks + 1 ))
  if [ "$1" != "$2" ]; then
    printf 'FAIL: %s — expected [%s], got [%s]\n' "$3" "$1" "$2"
    failures=$(( failures + 1 ))
  fi
}

# assert_range <label> <min> <max> <sample>
# Asserts the single sample falls within [min, max] inclusive.
assert_range() {
  checks=$(( checks + 1 ))
  # $1=label $2=min $3=max $4=sample
  if (( $4 < $2 || $4 > $3 )); then
    printf 'FAIL: %s — %s outside [%s, %s]\n' "$1" "$4" "$2" "$3"
    failures=$(( failures + 1 ))
  fi
}

# assert_in <haystack> <needle> <label>
assert_in() {
  checks=$(( checks + 1 ))
  case "$1" in
    *"$2"*) : ;;
    *) printf 'FAIL: %s — [%s] not found in output\n' "$3" "$2"
       failures=$(( failures + 1 )) ;;
  esac
}

# assert_not_in <haystack> <needle> <label>
assert_not_in() {
  checks=$(( checks + 1 ))
  case "$1" in
    *"$2"*) printf 'FAIL: %s — [%s] unexpectedly present\n' "$3" "$2"
            failures=$(( failures + 1 )) ;;
  esac
}

# assert_in_range_runs <label> <min> <max> <n> <attempt> [base] [max] [factor]
# Run backoff_interval n times and assert every result is within [min, max].
assert_in_range_runs() {
  local label="$1" min="$2" max="$3" n="$4"
  shift 4
  local v
  for (( i = 0; i < n; i++ )); do
    v="$(backoff_interval "$@")"
    assert_range "$label" "$min" "$max" "$v"
    # Must be a non-negative integer.
    case "$v" in
      ''|*[!0-9]*)
        printf 'FAIL: %s — not a non-negative integer: [%s]\n' "$label" "$v"
        failures=$(( failures + 1 )) ;;
    esac
  done
}

# assert_category <expected> <exit_code> <stderr_text> <label>
assert_category() {
  assert_eq "$1" "$(classify_push_error "$2" "$3")" "$4"
}

echo "== backoff =="
# base=1, factor=2: term(attempt) = 2^(attempt-1). Full jitter puts the result
# in [term, 2*term]. Run 300 times each; every sample must stay in bounds.
assert_in_range_runs "attempt=1 (term 1..2)" 1 2 300 1
assert_in_range_runs "attempt=2 (term 2..4)" 2 4 300 2
assert_in_range_runs "attempt=3 (term 4..8)" 4 8 300 3
assert_in_range_runs "attempt=5 (term 16..32)" 16 32 300 5

# max_seconds caps the exponential term. With max=30, attempt 6 would be 32
# before jitter, so the result is capped to [30, 60].
assert_in_range_runs "attempt=6 capped at 30" 30 60 300 6 1 30 2

# Custom factor: base=2, factor=3, attempt=3 -> term = 2*3*3 = 18.
assert_in_range_runs "factor=3 attempt=3 (term 18..36)" 18 36 300 3 2 100 3

echo "== classify_push_error =="
assert_category "race"   128 '! [rejected]         main -> main (non-fast-forward)\nerror: failed to push some refs' 'non-fast-forward'
assert_category "race"   128 'To https://github.com/x/y.git\n - [rejected]        main -> main (non-fast-forward)' 'non-fast-forward variant'
assert_category "race"   128 'error: Updates were rejected because the remote contains work that does not exist locally.' 'updates were rejected'

assert_category "auth"   128 'remote: Permission denied.x-access-token. fatal: Authentication failed' 'authentication required'
assert_category "auth"   128 'fatal: Authentication failed for https://github.com/x/y.git' 'fatal: Authentication failed'
assert_category "auth"   128 'remote: Invalid username or password.' 'invalid username'

assert_category "network" 128 'fatal: Could not read from remote repository.' 'could not read from remote repository'
assert_category "network" 128 'remote: Connection timed out.' 'connection timed out'
assert_category "network" 128 'curl: (56) RPC failed; curl send. transfer closed.' 'rpc failed / transfer closed'
assert_category "network" 128 'fatal: unable to access https://github.com/x/y.git: TLS handshake failed' 'unable to access / tls'

assert_category "fatal"  128 'error: object abc123 not found.' 'unknown error -> fatal'
assert_category "fatal"  2 'some unexpected failure' 'non-128 exit, unknown -> fatal'

# Empty message falls back to the exit code.
assert_category "network" 128 '' 'empty message, exit 128 -> network'
assert_category "fatal"   1 '' 'empty message, exit 1 -> fatal'

echo "== is_transient_error =="
if is_transient_error race; then assert_eq 0 0 "race is transient"; else assert_eq 1 0 "race is transient"; fi
if is_transient_error network; then assert_eq 0 0 "network is transient"; else assert_eq 1 0 "network is transient"; fi
if is_transient_error auth; then assert_eq 0 1 "auth is not transient"; else assert_eq 1 1 "auth is not transient"; fi
if is_transient_error fatal; then assert_eq 0 1 "fatal is not transient"; else assert_eq 1 1 "fatal is not transient"; fi

echo "== git_push_with_retry (control flow, mock git) =="
# git-push-retry.sh pulls in backoff.sh + transient-errors.sh itself.
# shellcheck disable=SC1091
source "$HERE/git-push-retry.sh"

# Mock git that records push attempts in a counter file, so the retry loop's
# re-clone-and-retry path is exercised without a real server (this box has no
# git-receive-pack). Fails while the invocation count is <= PUSH_FAIL.
MOCK_BIN="$(mktemp -d)/bin"
mkdir -p "$MOCK_BIN"
cat > "$MOCK_BIN/git" <<'MOCK'
#!/usr/bin/env bash
sub="$1"; shift
[ "$sub" = "-C" ] && { sub="$2"; shift 2; }
case "$sub" in
  clone) mkdir -p "${@: -1}" ;;
  config) : ;;
  add) : ;;
  commit) : ;;
  push)
    n=0; [ -f "$PUSH_COUNT_FILE" ] && n="$(cat "$PUSH_COUNT_FILE")"
    n=$((n + 1)); echo "$n" > "$PUSH_COUNT_FILE"
    if (( n <= ${PUSH_FAIL:-0} )); then
      case "${PUSH_SCENARIO:-race}" in
        auth) echo "fatal: Authentication failed" >&2 ;;
        *)    echo "error: [rejected]  main -> main (non-fast-forward)" >&2 ;;
      esac
      exit 128
    fi
    ;;
esac
MOCK
chmod +x "$MOCK_BIN/git"
export PATH="$MOCK_BIN:$PATH"
TEST_WORK="$(mktemp -d)"
trap 'rm -rf "$TEST_WORK"' EXIT

# Run git_push_with_retry, capturing combined output and exit code without
# aborting the script under set -e.
LAST_OUT=""
LAST_RC=0
run_gpw() {
  set +e
  LAST_OUT="$(git_push_with_retry 2>&1)"
  LAST_RC=$?
  set -e
}

setup_env() {
  export PUSH_COUNT_FILE="$TEST_WORK/_push_count"
  export PUSH_URL="file:///tmp/does-not-matter.git"
  export PUSH_REPO="$TEST_WORK/_idx"
  export PUSH_TOKEN="tok"
  export PUSH_BRANCH="main"
  export MAX_ATTEMPTS="8"
  export REPO_NAME="demo"
  rm -f "$PUSH_COUNT_FILE"
  export PUSH_USER_NAME="github-actions[bot]"
  export PUSH_USER_EMAIL="github-actions[bot]@users.noreply.github.com"
}

# index_update is provided by the caller; here it returns a code the test
# controls, so we exercise the lib's handling of each return value.
INDEX_RC=0
index_update() { return "$INDEX_RC"; }

# committed (0) + push ok -> success
setup_env; INDEX_RC=0; export PUSH_FAIL=0; export PUSH_SCENARIO=race
run_gpw
assert_eq 0 "$LAST_RC" "committed: exit 0"
assert_in "$LAST_OUT" "Pushed index update for demo (attempt 1)" "committed: push log"

# nothing to push (1) -> success, no retry
setup_env; INDEX_RC=1; export PUSH_FAIL=0; export PUSH_SCENARIO=race
run_gpw
assert_eq 0 "$LAST_RC" "no-change: exit 0"
assert_in "$LAST_OUT" "No index changes for demo" "no-change: log"
assert_not_in "$LAST_OUT" "retrying" "no-change: no retry"

# hook error (2) -> fatal, propagated
setup_env; INDEX_RC=2; export PUSH_FAIL=0; export PUSH_SCENARIO=race
run_gpw
assert_eq 2 "$LAST_RC" "hook-error: exit 2"
assert_in "$LAST_OUT" "::error::index_update failed (exit 2)" "hook-error: log"

# lost race (1 fail) -> re-clone, retry, succeed
setup_env; INDEX_RC=0; export PUSH_FAIL=1; export PUSH_SCENARIO=race
run_gpw
assert_eq 0 "$LAST_RC" "race: exit 0"
assert_in "$LAST_OUT" "Push rejected (race), retrying (1/8)" "race: retry log"
assert_in "$LAST_OUT" "Pushed index update for demo (attempt 2)" "race: retry push log"

# auth failure -> not transient, fail fast, single attempt
setup_env; INDEX_RC=0; export PUSH_FAIL=1; export PUSH_SCENARIO=auth
run_gpw
assert_eq 1 "$LAST_RC" "auth: exit 1"
assert_in "$LAST_OUT" "push rejected with non-transient error (auth) -- not retrying" "auth: log"

# exhaust attempts -> fail (MAX_ATTEMPTS=2 keeps the backoff sleeps short)
setup_env; INDEX_RC=0; export PUSH_FAIL=999; export PUSH_SCENARIO=race
export MAX_ATTEMPTS=2
run_gpw
assert_eq 1 "$LAST_RC" "exhaust: exit 1"
assert_in "$LAST_OUT" "push rejected after 2 attempts" "exhaust: log"
assert_not_in "$LAST_OUT" "Pushed" "exhaust: never pushed"

echo
if (( failures == 0 )); then
  echo "PASS: $checks checks passed"
  exit 0
fi
printf 'FAIL: %d of %d checks failed\n' "$failures" "$checks"
exit 1
