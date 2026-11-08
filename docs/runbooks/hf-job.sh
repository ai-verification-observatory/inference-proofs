#!/usr/bin/env bash
# One development job of the harness on Hugging Face Jobs, inside a container the provider
# started from a pinned adapter image, or from an engine image the job installs the adapter into
# (IPROOFS_DEV_IMAGE below) (docs/runbooks/hf-jobs.md, RFC-0006 §Hosted execution).
# The job's command clones this repository at IPROOFS_COMMIT and runs this script from it:
#
#   hf-job.sh probe                          host probe, harness install, binding check, self-test
#   hf-job.sh run SYSTEM STEP [STEP...]      the same, then each STEP in order
#
# A STEP is WORKLOAD:REPETITIONS or WORKLOAD:REPETITIONS:controls, for example
# `fp-maverick-w1024-b1:2:controls`. Every run is a development run on prover-h200-hosted
# (--allow-nonconforming until RFC-0006 Q5 pins the driver), written outside the checkout and
# never copied into results/ (POL-4).
#
# Environment (set with `hf jobs run -e`):
#   IPROOFS_COMMIT        the full commit hash the job command checked out (required)
#   IPROOFS_JOB_BUDGET_S  the seconds this script may use: the job's --timeout less an allowance
#                         for the image pull (hf-jobs.md passes timeout - 600); fetches and runs
#                         stop RESERVE seconds before it, so the upload still happens (default 1200)
#   IPROOFS_UPLOAD_DIR    a writable storage bucket mounted in the job (`hf jobs run -v
#                         hf://buckets/<namespace>/<bucket>:/upload`); out/ is copied into it, and
#                         no token enters the container
#   IPROOFS_UPLOAD        fallback when no bucket is mounted: a private dataset repository id,
#                         written with the HF_TOKEN secret (--secrets-file); see hf-jobs.md for
#                         who can read that secret in the container
#   IPROOFS_LABEL         a short label for the upload folder (default: the mode)
#   IPROOFS_GPU           the bound GPU index (default: the probe's suggestion, else 0)
#   IPROOFS_DEV_IMAGE     a development run from the public engine image the job was started
#                         from, <repository>@sha256:<digest>: systems/SYSTEM/dev_install.py puts
#                         the adapter files from this checkout where the Dockerfile puts them and
#                         checks the engine on the bound GPU, and the runs pass `--image
#                         IPROOFS_DEV_IMAGE --keep-io` (recorded as local/<that image>,
#                         digest_kind config; the io directory, with the engine's raw responses,
#                         stays in the run directory and is uploaded if it holds no weights)
# shellcheck disable=SC2329  # finish and upload run from the EXIT trap
set -uo pipefail

START=$(date +%s)
REPO=$(cd "$(dirname "$0")/../.." && pwd)
WORK=$(dirname "$REPO")
OUT="$WORK/out"                      # what the upload sends: logs, probe, self-test, runs
DEV="$OUT/dev-results"               # the harness's --results, outside the checkout
RELEASE=v0.1
PROFILE=prover-h200-hosted
PROVIDER="Hugging Face Jobs"
BUDGET=${IPROOFS_JOB_BUDGET_S:-1200}
RESERVE=900                          # seconds kept for the upload at the end
IO_KEEP_MAX_K=1048576                # a development run's io/ is uploaded only without a file
                                     # above 1 GiB or a weights file (prune)
MODE=${1:-}
[ $# -gt 0 ] && shift
mkdir -p "$OUT" "$DEV" "$WORK/home" "$WORK/hf-home"
exec > >(tee -a "$OUT/job.log") 2>&1
TEE=$!
# The images' user 10001 has no home directory; huggingface_hub keeps its cache and locks under
# HF_HOME. The hosted runner gives the adapter the image's own environment, not this one.
export HOME="$WORK/home" HF_HOME="$WORK/hf-home"
export UV_CACHE_DIR="$WORK/uv-cache" IPROOFS_CACHE="$WORK/cache"
PY="$REPO/.venv/bin/python"
IP="$REPO/.venv/bin/iproofs"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
left() { echo $((START + BUDGET - RESERVE - $(date +%s))); }

prune() {  # what a run stopped at the deadline leaves in its staging directory (runner._write)
  local dir part
  for dir in "$DEV"/*/*/.staging-*; do
    [ -d "$dir" ] || continue
    for part in io prover-ro verify controls-io commitment; do
      [ -e "$dir/$part" ] || continue
      if [ "$part" = io ] && [ -n "${IPROOFS_DEV_IMAGE:-}" ]; then
        # a development install's io is the capture (the engine's responses and log): kept,
        # unless it holds a weights file or any file above 1 GiB (another system's io may hold
        # a copy of the weights or a key)
        local big
        big=$(find "$dir/io" -type f \( -size +"${IO_KEEP_MAX_K}k" -o -name '*.gguf' \
          -o -name '*.safetensors' \) -print -quit)
        if [ -z "$big" ]; then
          log "prune: keeping $(du -sh "$dir/$part" | cut -f1) $(basename "$dir")/io (development run)"
          continue
        fi
        log "prune: io of a development run holds ${big#"$dir/"}: not kept"
      fi
      log "prune: $(du -sh "$dir/$part" | cut -f1) $(basename "$dir")/$part (weights copy, scratch, prover key)"
      rm -rf "${dir:?}/$part"
    done
  done
}

upload() {
  local status=$?
  prune
  local folder
  folder="runs/$(date -u +%Y%m%dT%H%M%SZ)-${IPROOFS_LABEL:-$MODE}"
  if [ -n "${IPROOFS_UPLOAD_DIR:-}" ]; then
    local dest="$IPROOFS_UPLOAD_DIR/$folder"
    log "upload: out/ to the mounted bucket, folder $folder"
    if ! mkdir -p "$dest"; then
      log "upload: cannot create the folder; exit $status"
      return
    fi
    # the small files first, so a slow copy of the runs still leaves the log and the probe
    cp "$OUT"/*.json "$OUT/job.log" "$dest/" 2>/dev/null || true
    if cp -R "$DEV" "$dest/"; then
      log "upload: done; exit $status"
    else
      log "upload: failed; exit $status"
    fi
    cp "$OUT/job.log" "$dest/" 2>/dev/null || true
    return
  fi
  if [ -z "${IPROOFS_UPLOAD:-}" ] || [ -z "${HF_TOKEN:-}" ]; then
    log "upload: skipped (no IPROOFS_UPLOAD_DIR, and IPROOFS_UPLOAD or HF_TOKEN not set); exit $status"
    return
  fi
  log "upload: out/ to dataset $IPROOFS_UPLOAD, folder $folder; exit $status"
  local py="$PY"
  [ -x "$py" ] || py="uv run --no-project --with huggingface_hub==0.36.2 python"
  local keep_io=0  # prune has removed every io/ that is not to leave the job
  [ -n "${IPROOFS_DEV_IMAGE:-}" ] && keep_io=1
  IPROOFS_FOLDER="$folder" IPROOFS_OUT="$OUT" IPROOFS_KEEP_STAGING_IO="$keep_io" $py - <<'EOF' \
    || log "upload: failed"
import os
from huggingface_hub import HfApi

api = HfApi()  # reads HF_TOKEN from the environment; it is never printed
repo, out, folder = os.environ["IPROOFS_UPLOAD"], os.environ["IPROOFS_OUT"], os.environ["IPROOFS_FOLDER"]
message = "development run (docs/runbooks/hf-jobs.md)"
ignore = [f"**/.staging-*/{part}/**" for part in ("prover-ro", "verify", "controls-io", "commitment")]
if os.environ.get("IPROOFS_KEEP_STAGING_IO") != "1":  # a development run's io/ is its capture
    ignore.insert(0, "**/.staging-*/io/**")
# The dataset exists already (hf-jobs.md stage 0): a token scoped to it cannot create it.
# Two commits: the log, probe and self-test first, then the run directories.
api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=out, path_in_repo=folder,
                  allow_patterns=["*.json", "job.log"], commit_message=message)
api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=out, path_in_repo=folder,
                  allow_patterns=["dev-results/**"], ignore_patterns=ignore,
                  commit_message=message)
print("upload: done")
EOF
}
finish() {  # the EXIT trap
  upload
  exec >&- 2>&-
  wait "$TEE" 2>/dev/null || true   # let tee write the last lines of job.log
}
trap finish EXIT

cd "$REPO" || exit 2
log "commit $(git rev-parse HEAD) (asked ${IPROOFS_COMMIT:-unset}); mode $MODE; budget ${BUDGET} s; uid $(id -u)"
if [ "$(git rev-parse HEAD)" != "${IPROOFS_COMMIT:-}" ]; then
  log "the checkout is not IPROOFS_COMMIT; stopping"
  exit 2
fi
if [ -n "${IPROOFS_UPLOAD_DIR:-}" ]; then
  if mkdir -p "$IPROOFS_UPLOAD_DIR/runs" 2>/dev/null && [ -w "$IPROOFS_UPLOAD_DIR/runs" ]; then
    log "upload bucket: writable"
  else
    log "upload bucket: NOT writable by uid $(id -u); nothing will leave this job"
  fi
fi

log "probe"
python3 docs/runbooks/host-probe.py --profile "$PROFILE" --work "$WORK" > "$OUT/probe.json"
log "probe exit $? (1: a profile requirement failed; see FAIL lines above)"
GPU=${IPROOFS_GPU:-$(python3 -c 'import json, sys
rows = json.load(open(sys.argv[1])).get("requirements") or []
found = [r["found"] for r in rows if r["id"] == "suggested_gpu_index"]
print(found[0] if found and found[0] is not None else 0)' "$OUT/probe.json" 2>/dev/null)}
GPU=${GPU:-0}
log "bound GPU $GPU"

# An engine image (IPROOFS_DEV_IMAGE) has no uv: the pinned release, its sha256 checked. An
# adapter image has its own (hf-jobs.md), so nothing is downloaded for one.
UV_VERSION=0.11.18
UV_SHA256=588f3e360f69ce02b6982aa99f2240e803933a6b7e176ac01617830adf955add
if [ -n "${IPROOFS_DEV_IMAGE:-}" ] && ! command -v uv >/dev/null; then
  log "uv: not in the image; uv $UV_VERSION from its GitHub release, sha256 checked"
  UV_DIR="$WORK/uv-$UV_VERSION"
  mkdir -p "$UV_DIR"
  if ! curl -fsSL --retry 3 -o "$WORK/uv.tar.gz" \
      "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz" \
    || ! echo "$UV_SHA256  $WORK/uv.tar.gz" | sha256sum -c --quiet - \
    || ! tar -xzf "$WORK/uv.tar.gz" -C "$UV_DIR" --strip-components=1; then
    log "uv: download or check failed; stopping"
    exit 3
  fi
  export PATH="$UV_DIR:$PATH"
fi
uv --version
log "install the harness"
if ! uv sync --frozen --no-dev --extra gpu --extra fetch --extra prompts; then
  log "uv sync failed; stopping"
  exit 3
fi
"$IP" --version
if ! "$PY" -c 'import huggingface_hub, pynvml, tokenizers'; then
  log "an extra of the harness is missing (gpu, fetch or prompts); stopping"
  exit 3
fi

log "binding check: the CPUs iproofs run --gpu $GPU binds on $PROFILE"
"$PY" - "$GPU" "$PROFILE" "$RELEASE" <<'EOF'
import sys
from pathlib import Path

from iproofs.model import load_reference
from iproofs.provenance import Host
from iproofs.runner import GpuEnvironment
from iproofs.schema import SchemaRegistry

gpu, profile, release = int(sys.argv[1]), sys.argv[2], sys.argv[3]
root = Path.cwd()
found = load_reference(release, root, SchemaRegistry.from_tree(root / "schema")).profiles[profile]
binding = GpuEnvironment(gpu, Host(hosted=True), found.cpu.logical_cpus_on_gpu_numa_node).binding
print(f"binding: {len(binding.prover)} prover CPUs on NUMA node {binding.mems[0]}, "
      f"{len(binding.verifier)} verifier CPUs")
EOF
BOUND=$?
log "binding check exit $BOUND (not 0: every iproofs run on this GPU refuses to start)"

log "hosted self-test (RFC-0011)"
env -u HF_TOKEN "$IP" machine-record --hosted --gpu "$GPU" --provider "$PROVIDER" --selftest \
  --results "$DEV" > "$OUT/selftest.json"
log "self-test exit $?"

[ "$MODE" = probe ] && exit 0
if [ "$MODE" != run ] || [ $# -lt 2 ]; then
  log "usage: hf-job.sh probe | hf-job.sh run SYSTEM WORKLOAD:REPETITIONS[:controls]..."
  exit 2
fi
if [ "$BOUND" -ne 0 ]; then
  log "the binding check failed; stopping before any weights are fetched"
  exit 3
fi
SYSTEM=$1
shift
image_args=()
if [ -n "${IPROOFS_DEV_IMAGE:-}" ]; then
  log "development install of $SYSTEM into $IPROOFS_DEV_IMAGE, from this checkout"
  if [ ! -f "systems/$SYSTEM/dev_install.py" ] \
    || ! python3 "systems/$SYSTEM/dev_install.py" "$IPROOFS_DEV_IMAGE" "$GPU"; then
    log "the development install or its engine check failed (or $SYSTEM has none); stopping before any weights"
    exit 3
  fi
  image_args=(--image "$IPROOFS_DEV_IMAGE" --keep-io)
fi
failed=0
for step in "$@"; do
  IFS=: read -r workload reps controls <<< "$step"
  remaining=$(left)
  if [ "$remaining" -le 600 ]; then
    log "$remaining s left before the reserve; $workload not started"
    failed=1
    break
  fi
  log "fetch-model $workload, at most $remaining s"
  if ! env -u HF_TOKEN timeout --kill-after=60 "$remaining" "$IP" fetch-model "$workload"; then
    log "fetch-model $workload failed or reached the deadline; next step"
    failed=1
    continue
  fi
  remaining=$(left)
  if [ "$remaining" -le 600 ]; then
    log "$remaining s left before the reserve; $workload not started"
    failed=1
    break
  fi
  extra=()
  [ "${controls:-}" = controls ] && extra=(--control-suite)
  log "run $SYSTEM $workload x${reps:-1} ${extra[*]:-} ${image_args[*]:-}, at most $remaining s"
  env -u HF_TOKEN timeout --kill-after=60 "$remaining" "$IP" run --system "$SYSTEM" \
    --workload "$workload" --profile "$PROFILE" --hosted --gpu "$GPU" --provider "$PROVIDER" \
    --repetitions "${reps:-1}" --allow-nonconforming --results "$DEV" \
    ${extra[@]+"${extra[@]}"} ${image_args[@]+"${image_args[@]}"}  # empty arrays under bash 3.2 too
  rc=$?
  # 0 all repetitions completed; 4 a repetition was recorded as failed; 124 or 137 stopped at
  # the job's deadline: its staging directory is uploaded without io/, the scratch directories
  # and the commitment store (prune); other: a harness error.
  log "run $SYSTEM $workload exit $rc"
  [ "$rc" -eq 0 ] || failed=1
done
exit "$failed"
