#!/usr/bin/env bash
# git-push-retry.sh — generic git push with race-aware retry.
#
# Wraps the clone -> update -> commit -> push cycle that several tuna-os
# workflows perform against a shared branch (the canonical case is
# publish-flatpak-index pushing an app's entry into tuna-os/docs, where every
# app repo races to write the same branch). The retry loop re-clones onto the
# new tip, backs off with jitter, and only retries transient failures (a lost
# race or a transport error); auth failures and anything else fail fast.
#
# Sourcing this file also sources backoff.sh and transient-errors.sh, so a
# caller needs only this one include.
#
# Callers configure the run through environment variables and provide a single
# hook function:
#
#   Env (all required except where noted):
#     PUSH_URL        clone URL of the repo to push into
#                     (https://github.com/<owner>/<repo>.git)
#     PUSH_REPO       path to the working copy
#     PUSH_TOKEN      token used for header-based auth
#     PUSH_BRANCH     branch to push to (default: main)
#     MAX_ATTEMPTS    max push attempts (default: 8)
#     REPO_NAME       optional label for log lines
#     PUSH_USER_NAME  commit author name (default: github-actions[bot])
#     PUSH_USER_EMAIL commit author email (default: github-actions[bot]@...)
#
#   Hook (required):
#     index_update    runs inside $PUSH_REPO; regenerates the entry, stages it
#                     with `git add`, and commits only when there is a change.
#                     Return 0 when it committed something (proceed to push),
#                     1 when there was nothing to push (success), or a
#                     non-zero code on any error (e.g. a failing update script).
#                     The non-zero error code is fatal and propagated, not
#                     read as "nothing to push".
#
# Exit status: 0 pushed (or nothing to push); 1 exhausted attempts or a
# non-transient failure.

# Resolve this file's directory so the sourced libraries are found regardless
# of the caller's working directory. SC1091 (untracked include) is expected
# here and excluded in the org lint gate.
_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$_lib_dir/backoff.sh"
# shellcheck disable=SC1091
source "$_lib_dir/transient-errors.sh"

# clone_repo <url> <dest> <token>
# Clone <url> into <dest> with header-based auth (so the token never lands in
# .git/config, `git remote -v`, or process listings) and a fixed commit identity.
# Re-clone clears the destination first, which is what the retry loop needs to
# replay the update onto a fresh tip.
clone_repo() {
  local url="$1"
  local dest="$2"
  local token="$3"

  rm -rf "$dest"
  git clone --depth 1 "$url" "$dest"
  git -C "$dest" config --local http.extraheader \
    "AUTHORIZATION: basic $(printf 'x-access-token:%s' "$token" | base64 -w0)"
  git -C "$dest" config user.name "${PUSH_USER_NAME:-github-actions[bot]}"
  git -C "$dest" config user.email "${PUSH_USER_EMAIL:-github-actions[bot]@users.noreply.github.com}"
}

# git_push_with_retry
# Drive the clone/update/commit/push cycle with race-aware retry. See the file
# header for the required env vars and the index_update hook.
git_push_with_retry() {
  local branch="${PUSH_BRANCH:-main}"
  local max_attempts="${MAX_ATTEMPTS:-8}"
  local attempt=1
  local push_output push_code category

  clone_repo "$PUSH_URL" "$PUSH_REPO" "$PUSH_TOKEN"

  while :; do
    # Caller regenerates, stages, and commits only if there is a change.
    #   0 committed something -> proceed to push
    #   1 nothing to push     -> success, done
    #   !1 error              -> fatal, propagate (a failing update script
    #                            must abort, not be read as "no change")
    local hook_rc=0
    index_update || hook_rc=$?
    case "$hook_rc" in
      0) : ;;
      1) echo "No index changes for ${REPO_NAME:-repo}"; return 0 ;;
      *) echo "::error::index_update failed (exit $hook_rc)" >&2; return "$hook_rc" ;;
    esac

    # Capture combined push output; the assignment's status is git's exit code.
    if push_output="$(git -C "$PUSH_REPO" push origin HEAD:"$branch" 2>&1)"; then
      echo "Pushed index update${REPO_NAME:+ for $REPO_NAME} (attempt $attempt)"
      return 0
    fi
    push_code=$?

    if (( attempt >= max_attempts )); then
      echo "::error::push rejected after $max_attempts attempts (concurrent writers to $PUSH_URL) -- giving up" >&2
      echo "$push_output" >&2
      return 1
    fi

    category="$(classify_push_error "$push_code" "$push_output")"
    if ! is_transient_error "$category"; then
      echo "::error::push rejected with non-transient error ($category) -- not retrying" >&2
      echo "$push_output" >&2
      return 1
    fi

    echo "Push rejected ($category), retrying ($attempt/$max_attempts)..."
    backoff_sleep "$attempt"
    # Lost the race (or lost the connection): re-clone onto the new tip and
    # replay this app's entry against it.
    clone_repo "$PUSH_URL" "$PUSH_REPO" "$PUSH_TOKEN"
    attempt=$(( attempt + 1 ))
  done
}
