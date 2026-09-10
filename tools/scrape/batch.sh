#!/bin/sh
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Scrape one product in batches, going quiet between them.
#
# Why batches rather than one long run: SUMO's edge rate-limits aggressively,
# a ban lasts minutes, and requests made during one appear to restart the
# window (see CLAUDE.md). A single unbroken pass over a few hundred articles is
# the thing most likely to trip it. So this fetches a batch, then waits a random
# 5-15 minutes before asking for more.
#
# Each pass re-enumerates and skips whatever is already on disk, so a batch is
# just the resumable scraper with a bigger `--limit`. Interrupting it loses
# nothing; re-running continues from the same place.
#
#   tools/scrape/batch.sh firefox corpus-other 60 /tmp/anon.txt
#   tools/scrape/batch.sh firefox corpus-other 40    # 40 at a time
#   tools/scrape/batch.sh --slugs /tmp/templates.txt corpus-other/templates 60
#
# Stops when a pass fetches nothing new, which means everything listed for the
# product is on disk.
#
# **On failure it stops immediately** and writes <outdir>/.batch-state — where it
# got to and why — rather than retrying into a rate limit that retrying prolongs.
# Resuming is the same command again; the scraper skips what is already fetched.
set -eu

usage='usage: batch.sh <product|--slugs FILE> <outdir> [batch-size] [allow-list]'
product=''
slugfile=''
if [ "${1:-}" = '--slugs' ]; then
  slugfile=${2:?$usage}
  shift 2
else
  product=${1:?$usage}
  shift
fi
out=${1:?$usage}
batch=${2:-60}
# An anonymous `--list-only` dump. Passing one is strongly advised for a product
# scrape: it runs signed in, so the product's listing includes its unpublished
# drafts. Irrelevant with --slugs, where the slugs are already chosen.
allow=${3:-}

cd "$(dirname "$0")"
repo=$(cd ../.. && pwd)
# `--out` may be absolute or repo-relative; scrape.mjs resolves it the same way.
# Naive concatenation put the state file in <repo>/tmp/... for an absolute path.
case $out in
  /*) outdir=$out ;;
  *) outdir="$repo/$out" ;;
esac
state="$outdir/.batch-state"
log=$(mktemp)
trap 'rm -f "$log"' EXIT

# Being killed is a failure point too, and the one most likely to happen
# unattended: this run was terminated mid-pause when the machine ran low on
# memory, and left no record at all. Write the same note on a signal.
count_on_disk() {
  find "$outdir" -name '*.wiki' 2>/dev/null | wc -l | tr -d ' '
}

resume_cmd() {
  if [ -n "$slugfile" ]; then
    echo "  tools/scrape/batch.sh --slugs $slugfile $out $batch"
  else
    echo "  tools/scrape/batch.sh $product $out $batch"
  fi
}

# $1 is the headline; anything already in $extra is appended verbatim.
write_state() {
  mkdir -p "$outdir"
  {
    echo "$1"
    echo
    echo "when:        $(date '+%Y-%m-%d %H:%M:%S %Z')"
    echo "target:      ${product:-$slugfile}"
    echo "out:         $out"
    echo "batch size:  $batch"
    echo "reached:     pass ${pass:-?} (--limit ${limit:-?})"
    echo "on disk:     $(count_on_disk) .wiki files"
    [ -n "${extra:-}" ] && printf '\n%s\n' "$extra"
    echo
    echo "resume with (skips what is already on disk):"
    resume_cmd
  } >"$state"
}

on_signal() {
  extra='Nothing was retried and no batch failed — the run was cut short.'
  write_state 'batch.sh was terminated by a signal, not by a scrape failure.'
  printf '\n=== signalled. state written to %s\n' "$state"
  exit 143
}
trap on_signal TERM INT

limit=$batch
pass=1
while :; do
  printf '\n=== pass %d: up to %d articles (%s)\n' "$pass" "$limit" "$(date +%H:%M:%S)"

  # No pipe into tee: the exit status of a pipeline is the last command's, so a
  # scraper failure would read as success. Print the log afterwards instead.
  # --limit slices the same ordered list every pass and the scraper skips what is
  # already on disk, so a bigger limit each time is exactly "the next batch",
  # whether the list came from a product listing or a file.
  if node scrape.mjs --base https://support.mozilla.org \
      ${slugfile:+--slugs "$slugfile"} ${product:+--products "$product"} \
      --out "$out" --limit "$limit" \
      ${allow:+--only "$allow"} >"$log" 2>&1; then
    cat "$log"
  else
    rc=$?
    cat "$log"
    extra=$(
      echo "exit status:  $rc"
      echo "last fetched: $(awk '/✓/ { last = $2 } END { print (last ? last : "(none this pass)") }' "$log")"
      echo
      echo "why it stopped:"
      grep -E '^(FAILED|Error)' "$log" | tail -3 || tail -3 "$log"
      echo
      echo "If it was a rate limit, wait it out first — requests made during a ban"
      echo "appear to restart the window, so an early retry costs more time."
    )
    write_state 'batch.sh stopped on a failure — nothing was retried.'
    printf '\n=== stopped. state written to %s\n' "$state"
    cat "$state"
    exit "$rc"
  fi

  new=$(awk '/^fetched/ {print $2; exit}' "$log")
  : "${new:=0}"
  printf '=== pass %d fetched %s (on disk: %s)\n' "$pass" "$new" "$(count_on_disk)"
  if [ "$new" -eq 0 ]; then
    printf '=== nothing new; %s is complete\n' "${product:-$slugfile}"
    rm -f "$state"
    break
  fi

  limit=$((limit + batch))
  pass=$((pass + 1))
  # Random inside the window rather than a fixed interval: a limiter that is
  # watching for a pattern sees less of one, and nothing here needs a schedule.
  nap=$(awk 'BEGIN { srand(); print 300 + int(rand() * 601) }')
  printf '=== pausing %ds before the next batch (%s)\n' "$nap" "$(date +%H:%M:%S)"
  sleep "$nap"
done
