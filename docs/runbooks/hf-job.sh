#!/usr/bin/env bash
# One development job of the harness on Hugging Face Jobs, inside a container the provider
# started from a pinned adapter image, or from an engine image the job installs the adapter into
# (IPROOFS_DEV_IMAGE below) (docs/runbooks/hf-jobs.md, RFC-0006 §Hosted execution).
# The job's command clones this repository at IPROOFS_COMMIT and runs this script from it:
#
#   hf-job.sh probe                          host probe, harness install, binding check, self-test
#   hf-job.sh run SYSTEM STEP [STEP...]      the same, then each STEP in order
#   hf-job.sh seed SYSTEM RUN_PATH           the harness only, then the seed record of a stored
#                                            run's split control suite, written once
#   hf-job.sh controls SYSTEM RUN_PATH ID[,ID...]
#                                            probe and install, then one part of that suite
#   hf-job.sh merge SYSTEM RUN_PATH          the harness only, then controls.json from the parts
#   hf-job.sh fidelity RUNG                  Level 1: the rung's reference, controls and KL in the
#                                            ref-fidelity image (RFC-0018 FI-8, docs/runbooks/level-1.md)
#
# A STEP is WORKLOAD:REPETITIONS with options after further colons: `controls` (the control
# suite, in this job), `keep-io` (the run directory keeps io/, with its proofs, and its
# commitment store, and both are uploaded, so that `controls` jobs can run from the bucket;
# the proof archive under .archive/ is then left out, since io/proofs holds the same proof),
# `high` (a production-serving job at high load, RFC-0015 SRV-1), `sizing=N` (a matched
# production-serving sizing capture of N batches while system.yaml's batches_per_session_run is
# null, for `iproofs serving size-session`; it joins no overhead, RFC-0015 SRV-1) and `from=DIR`
# (replay the prompts of the run directory DIR, relative to the mounted bucket, RFC-0015 SRV-8),
# for example `fp-maverick-w1024-b1:2:controls`, `sash-l31-8b-c1024:1:keep-io`,
# `fp-maverick-w1024-b24:1:high:from=runs/X/dev-results/v0.1/flashprove/R` or
# `sash-l31-8b-c1024:1:sizing=50:from=runs/X/dev-results/v0.1/sash/R`. Level 1 (RFC-0018,
# docs/runbooks/level-1.md) adds `level=L1` (the run is one session of the level; REPETITIONS
# must be 1), `session=K` (its slot, 1 to 3) and `ladder` (a production-serving ladder run), for
# example `l1-l31-8b-p512-o512:1:level=L1:session=1:keep-io` or
# `l1-l31-8b-p512-o512:1:level=L1:ladder`; `perturbed` first commits the level's changed weights
# on this host for the Model check (C3, P1), so a full session with its controls is
# `l1-maverick-p512-o512:1:level=L1:session=1:perturbed:controls`. `keep-io` is
# refused for flashprove: its io/ holds a copy of the weights and its commitment store the
# prover's secret key. Every run is a development run on IPROOFS_PROFILE
# (--allow-nonconforming: the profile pins no driver, RFC-0006 Q5), written outside the checkout and
# never copied into results/ (POL-4). An upload that copied everything ends with upload.done in
# its bucket folder; `seed`, `controls` and `merge` refuse a stored run whose folder has none.
# Every mode uploads the same way: through the bucket API, checked file by file, when HF_TOKEN
# and IPROOFS_UPLOAD_BUCKET are set (prover and production-serving jobs alike).
#
# `seed`, `controls` and `merge` (RFC-0008 §Split suites) work on a stored run, RUN_PATH =
# runs/<UTC>-<label>/dev-results/<release>/SYSTEM/<run id> in the mounted bucket. `seed` runs
# `iproofs controls --draw-seed` and writes controls-seed.json into the stored run, once.
# `controls` copies the stored run (from IPROOFS_STORED_DIR, a read-only mount of it, if set),
# runs `iproofs controls --hosted --only ID[,ID...]` against the copy with the recorded seed,
# and uploads the part and the logs under controls/. With a GPU the job binds it and fetches
# the weights (prover-side ids); without one it is a verifier host, which runs verifier-side
# ids only. `merge` merges every part of that seed found under runs/*/controls/ and writes
# controls.json, and the parts under controls-parts/, into the stored run, once.
#
# Environment (set with `hf jobs run -e`):
#   IPROOFS_COMMIT        the full commit hash the job command checked out (required)
#   IPROOFS_JOB_BUDGET_S  the seconds this script may use: the job's --timeout less an allowance
#                         for the image pull (hf-jobs.md passes timeout - 600); fetches and runs
#                         stop RESERVE seconds before it, so the upload still happens (default 1200)
#   IPROOFS_UPLOAD_DIR    a writable storage bucket mounted in the job (`hf jobs run -v
#                         hf://buckets/<namespace>/<bucket>:/upload`); out/ is copied into it, and
#                         no token enters the container
#   IPROOFS_UPLOAD_BUCKET <namespace>/<bucket>: with the HF_TOKEN secret (--secrets-file), out/
#                         goes through the bucket API and is checked file by file (upload_api),
#                         for every mode and profile, in place of the copy to the mount
#   IPROOFS_UPLOAD_ARCHIVES  1: the API upload also sends the proof archives (*.tar)
#   IPROOFS_UPLOAD        fallback when no bucket is mounted: a private dataset repository id,
#                         written with the HF_TOKEN secret (--secrets-file); see hf-jobs.md for
#                         who can read that secret in the container
#   IPROOFS_LABEL         a short label for the upload folder (default: the mode)
#   IPROOFS_GPU           the bound GPU index (default: the probe's suggestion, else 0)
#   IPROOFS_PROFILE       the profile (default prover-h200-hosted); a serving profile
#                         (serving-h200x1-hosted, serving-h200x4-hosted, RFC-0006 R6) binds
#                         IPROOFS_GPUS
#   IPROOFS_GPUS          a serving profile's bound GPUs, comma-separated (default: 0 to its
#                         gpu.count - 1); the runner refuses another count than gpu.count
#   IPROOFS_DEV_IMAGE     a development run from the public engine image the job was started
#                         from, <repository>@sha256:<digest>: systems/SYSTEM/dev_install.py puts
#                         the adapter files from this checkout where the Dockerfile puts them and
#                         checks the engine on the bound GPU, and the runs pass `--image
#                         IPROOFS_DEV_IMAGE --keep-io` (recorded as local/<that image>,
#                         digest_kind config; the io directory, with the engine's raw responses,
#                         stays in the run directory and is uploaded if it holds no weights)
#   IPROOFS_STORED_DIR    controls only: a read-only mount of the stored run (`hf jobs run -v
#                         hf://buckets/<namespace>/<bucket>/RUN_PATH:/stored:ro`)
# shellcheck disable=SC2329  # finish and upload run from the EXIT trap
set -uo pipefail

START=$(date +%s)
REPO=$(cd "$(dirname "$0")/../.." && pwd)
WORK=$(dirname "$REPO")
OUT="$WORK/out"                      # what the upload sends: logs, probe, self-test, runs
DEV="$OUT/dev-results"               # the harness's --results, outside the checkout
RELEASE=${IPROOFS_RELEASE:-v0.1}  # v1.0 for Level 1 jobs (a step with level=L1 sets it too)
PROFILE=${IPROOFS_PROFILE:-prover-h200-hosted}
PROVIDER="Hugging Face Jobs"
BUDGET=${IPROOFS_JOB_BUDGET_S:-1200}
RESERVE=900                          # seconds kept for the upload at the end
IO_KEEP_MAX_K=1048576                # a development run's io/ is uploaded only without a file
                                     # above 1 GiB or a weights file (prune)
KEEP_IO=0                            # a step keeps io/: .archive stays out of the upload
MODE=${1:-}
[ $# -gt 0 ] && shift
has_opt() { case ":$1:" in *":$2:"*) return 0 ;; esac; return 1; }  # STEP options
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

dev_bytes() {  # the bytes copy_dev sends
  if [ "$KEEP_IO" = 1 ]; then
    du -sb --exclude=.archive "$DEV" | cut -f1
  else
    du -sb "$DEV" | cut -f1
  fi
}

copy_dev() {  # DEST: the self-test record, the run directories, then the proof archive
  local dest=$1 item failed=0
  mkdir -p "$dest" || return 1
  if [ -f "$DEV/.selftest.json" ]; then
    cp "$DEV/.selftest.json" "$dest/" || failed=1
  fi
  for item in "$DEV"/*; do
    [ -e "$item" ] || continue
    cp -R "$item" "$dest/" || failed=1
  done
  if [ -d "$DEV/.archive" ]; then
    if [ "$KEEP_IO" = 1 ]; then  # the same bytes as io/proofs/<first>; digests.txt keeps its digest
      log "upload: .archive left out ($(du -sh "$DEV/.archive" | cut -f1)): with keep-io, io/proofs holds that proof"
    else
      cp -R "$DEV/.archive" "$dest/" || failed=1
    fi
  fi
  return "$failed"
}

HFCLI_VERSION=2.4.0                  # the hf CLI the API upload runs (its bucket commands)
hfcli() { uv tool run --quiet --from "huggingface_hub==$HFCLI_VERSION" hf "$@"; }

verify_upload() {  # FOLDER: every file of out/ is in the bucket with its size (job.log excepted)
  local folder=$1
  hfcli buckets ls "$IPROOFS_UPLOAD_BUCKET" --recursive > "$WORK/remote.txt" 2>/dev/null || return 1
  python3 - "$OUT" "$folder" "$WORK/remote.txt" <<'PYEOF'
import os
import sys

out, folder, listing = sys.argv[1:]
archives = os.environ.get("IPROOFS_UPLOAD_ARCHIVES", "0") == "1"
remote = {}
for line in open(listing):
    parts = line.split()
    if len(parts) >= 2 and parts[0].isdigit():
        remote[parts[-1]] = int(parts[0])
wrong = []
for root, _dirs, files in os.walk(out):
    for name in files:
        path = os.path.join(root, name)
        rel = os.path.relpath(path, out)
        if rel in ("job.log", "upload.done") or (rel.endswith(".tar") and not archives):
            continue
        size = os.path.getsize(path)
        got = remote.get(f"{folder}/{rel}")
        if got != size:
            wrong.append((rel, size, got))
for rel, size, got in wrong[:20]:
    print(f"upload check: {rel}: {size} bytes here, {got} in the bucket")
print(f"upload check: {len(wrong)} of the files in out/ missing or of another size")
sys.exit(1 if wrong else 0)
PYEOF
}

upload_api() {  # STATUS FOLDER: through the bucket API, which returns once the files are sent
  local status=$1 folder=$2 ok=1
  local dest="hf://buckets/$IPROOFS_UPLOAD_BUCKET/$folder"
  local tars=(--exclude '*.tar')
  [ "${IPROOFS_UPLOAD_ARCHIVES:-0}" = 1 ] && tars=()
  log "upload: out/ through the bucket API to $dest (proof archives: ${IPROOFS_UPLOAD_ARCHIVES:-0})"
  # the records first (no proof archive, no io/), so they arrive even if a large file fails
  if hfcli buckets sync "$OUT" "$dest" --exclude '*.tar' --exclude '*/io/*' --quiet; then
    log "upload: records sent"
  else
    ok=0
    log "upload: records FAILED"
  fi
  if ! hfcli buckets sync "$OUT" "$dest" ${tars[@]+"${tars[@]}"} --quiet; then
    ok=0
    log "upload: large files FAILED"
  fi
  if [ "$ok" = 1 ] && verify_upload "$folder"; then
    printf 'dev-results bytes %s\n' "$(dev_bytes)" > "$OUT/upload.done"
    if hfcli buckets cp "$OUT/upload.done" "$dest/upload.done" --quiet; then
      log "upload: done and checked file by file ($(cat "$OUT/upload.done")); exit $status"
    else
      log "upload: sent and checked, but the upload.done marker FAILED; exit $status"
    fi
  else
    log "upload: FAILED or incomplete (see the check above); exit $status"
  fi
  hfcli buckets cp "$OUT/job.log" "$dest/job.log" --quiet || true
}

upload() {
  local status=$?
  prune
  local folder
  folder="runs/$(date -u +%Y%m%dT%H%M%SZ)-${IPROOFS_LABEL:-$MODE}"
  if [ -n "${HF_TOKEN:-}" ] && [ -n "${IPROOFS_UPLOAD_BUCKET:-}" ]; then
    upload_api "$status" "$folder"
    return
  fi
  if [ -n "${IPROOFS_UPLOAD_DIR:-}" ]; then
    log "upload: WARNING the bucket mount sends large files in the background and may drop them when the job ends (SASH r1, 2026-11-08); set HF_TOKEN and IPROOFS_UPLOAD_BUCKET for a checked upload"
    local dest="$IPROOFS_UPLOAD_DIR/$folder"
    log "upload: out/ to the mounted bucket, folder $folder"
    if ! mkdir -p "$dest"; then
      log "upload: cannot create the folder; exit $status"
      return
    fi
    # the small files first, so a slow copy of the runs still leaves the log and the probe
    cp "$OUT"/*.json "$OUT/job.log" "$dest/" 2>/dev/null || true
    [ -d "$OUT/controls" ] && cp -R "$OUT/controls" "$dest/"
    if copy_dev "$dest/dev-results"; then
      # what seed, controls and merge check first: this copy ended, with this many bytes
      printf 'dev-results bytes %s\n' "$(dev_bytes)" > "$dest/upload.done"
      log "upload: done ($(cat "$dest/upload.done")); exit $status"
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
  local keep_staging_io=0  # prune has removed every staging io/ that is not to leave the job
  [ -n "${IPROOFS_DEV_IMAGE:-}" ] && keep_staging_io=1
  IPROOFS_FOLDER="$folder" IPROOFS_OUT="$OUT" IPROOFS_KEEP_STAGING_IO="$keep_staging_io" \
    IPROOFS_KEEP_IO="$KEEP_IO" $py - <<'EOF' || log "upload: failed"
import os
from huggingface_hub import HfApi

api = HfApi()  # reads HF_TOKEN from the environment; it is never printed
repo, out, folder = os.environ["IPROOFS_UPLOAD"], os.environ["IPROOFS_OUT"], os.environ["IPROOFS_FOLDER"]
message = "development run (docs/runbooks/hf-jobs.md)"
ignore = [f"**/.staging-*/{part}/**" for part in ("prover-ro", "verify", "controls-io", "commitment")]
if os.environ.get("IPROOFS_KEEP_STAGING_IO") != "1":  # a development run's io/ is its capture
    ignore.insert(0, "**/.staging-*/io/**")
if os.environ.get("IPROOFS_KEEP_IO") == "1":  # io/proofs holds the archived proof
    ignore.append("dev-results/.archive/**")
# The dataset exists already (hf-jobs.md stage 0): a token scoped to it cannot create it.
# Two commits: the log, probe and self-test first, then the run directories.
api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=out, path_in_repo=folder,
                  allow_patterns=["*.json", "job.log", "controls/**"], commit_message=message)
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

# Arguments that can be refused before anything is installed or billed for long.
if [ "$MODE" = run ] && [ $# -ge 1 ]; then
  for step in "${@:2}"; do
    IFS=: read -r _ _ opts <<< "$step"
    has_opt "${opts:-}" keep-io || continue
    if [ "$1" = flashprove ]; then
      log "keep-io is refused for flashprove: io/ holds a weights copy, commitment/ the prover's key"
      exit 2
    fi
    # a kept SASH run uploads its 44.6 GB proof (the H100 run's manifest) and io/state, not the
    # .archive copy; the bucket's write speed is not documented: 3,600 s is enough for the proof
    # at 12.4 MB/s or more, an assumption (hf-jobs.md stage 2)
    RESERVE=3600
    KEEP_IO=1
  done
fi
stored_checks() {  # SYSTEM RUN_PATH: a stored run that seed, controls and merge can use
  CSYSTEM=$1 RUN_PATH=${2%/}
  if [ -z "${IPROOFS_UPLOAD_DIR:-}" ]; then
    log "$MODE reads the run from the mounted bucket: set IPROOFS_UPLOAD_DIR"
    exit 2
  fi
  case "$RUN_PATH" in
    runs/*/dev-results/*/"$CSYSTEM"/*) ;;
    *) log "RUN_PATH must be runs/<folder>/dev-results/<release>/$CSYSTEM/<run id>"; exit 2 ;;
  esac
  STORED="$IPROOFS_UPLOAD_DIR/$RUN_PATH"   # read-write: seed and merge write here, once
  local folder="${RUN_PATH%%/dev-results/*}"
  if [ ! -f "$STORED/run.json" ] || [ ! -f "$STORED/manifest.json" ]; then
    log "no stored run at $RUN_PATH (run.json and manifest.json)"
    exit 2
  fi
  if [ ! -f "$IPROOFS_UPLOAD_DIR/$folder/upload.done" ]; then
    log "the upload of $folder did not finish (no upload.done): its copy may be partial"
    exit 2
  fi
  if [ -e "$STORED/controls.json" ]; then
    log "$RUN_PATH already has controls.json: its suite has run (RFC-0008, once per configuration)"
    exit 2
  fi
}

record_seed() {  # FILE: the control_seed of a controls-seed.json, with the system python3
  python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["control_seed"])' "$1"
}

# Arguments of seed, controls and merge, refused before anything is installed or billed for long.
case "$MODE" in
  seed|merge)
    if [ $# -ne 2 ]; then
      log "usage: hf-job.sh $MODE SYSTEM RUN_PATH"
      exit 2
    fi
    stored_checks "$1" "$2"
    if [ "$MODE" = seed ] && [ -e "$STORED/controls-seed.json" ]; then
      log "$RUN_PATH already has controls-seed.json: its seed is drawn once (SPLIT-1)"
      exit 2
    fi
    if [ "$MODE" = merge ] && [ ! -f "$STORED/controls-seed.json" ]; then
      log "$RUN_PATH has no controls-seed.json: no part can have run"
      exit 2
    fi
    ;;
  controls)
    if [ $# -ne 3 ]; then
      log "usage: hf-job.sh controls SYSTEM RUN_PATH ID[,ID...]"
      exit 2
    fi
    stored_checks "$1" "$2"
    IDS=$3
    READ_FROM=${IPROOFS_STORED_DIR:-$STORED}   # a read-only mount of the run, if given
    if [ ! -d "$READ_FROM/io/proofs" ] || [ ! -d "$READ_FROM/commitment" ]; then
      log "no kept run at $RUN_PATH: it needs io/proofs and commitment/ (a run made with keep-io)"
      exit 2
    fi
    if [ ! -f "$READ_FROM/controls-seed.json" ]; then
      log "$RUN_PATH has no controls-seed.json: draw it once with hf-job.sh seed $CSYSTEM $RUN_PATH"
      exit 2
    fi
    known=" C1 C2 C3 C4 C5 C6 C7 C8 P1 P2 "
    if [ -f "systems/$CSYSTEM/controls.yaml" ]; then
      known+="$(sed -n 's/^  - id: "\(.*\)"$/\1/p' "systems/$CSYSTEM/controls.yaml" | tr '\n' ' ')"
    fi
    IFS=, read -ra asked <<< "$IDS"
    for id in "${asked[@]}"; do
      case "$known" in
        *" $id "*) ;;
        *) log "unknown control id '$id'; this suite is:$known"; exit 2 ;;
      esac
    done
    ;;
esac

if [ "$MODE" = seed ] || [ "$MODE" = merge ]; then
  # no probe, GPU or self-test: these read and write a few small files
  log "install the harness"
  if ! uv sync --frozen --no-dev; then
    log "uv sync failed; stopping"
    exit 3
  fi
  LOCAL="$WORK/stored/$(basename "$RUN_PATH")"
  mkdir -p "$LOCAL" "$OUT/controls"
  for f in run.json manifest.json controls-seed.json; do
    if [ -f "$STORED/$f" ]; then cp "$STORED/$f" "$LOCAL/"; fi
  done
  if [ "$MODE" = seed ]; then
    "$IP" controls "$LOCAL" --draw-seed || exit 2
    if [ -e "$STORED/controls-seed.json" ]; then  # another job drew one meanwhile
      log "$RUN_PATH has controls-seed.json now; this draw is discarded"
      exit 2
    fi
    cp "$LOCAL/controls-seed.json" "$STORED/controls-seed.json"
    cp "$LOCAL/controls-seed.json" "$OUT/controls/"
    log "seed $(record_seed "$STORED/controls-seed.json") written to $RUN_PATH/controls-seed.json"
    exit 0
  fi
  SEED=$(record_seed "$LOCAL/controls-seed.json")
  parts=()
  for part in "$IPROOFS_UPLOAD_DIR"/runs/*/controls/controls-part-"${SEED#0x}"-*.json; do
    [ -f "$part" ] || continue
    folder=$(basename "$(dirname "$(dirname "$part")")")
    mkdir -p "$WORK/parts/$folder"
    cp "$part" "$WORK/parts/$folder/"
    parts+=("$WORK/parts/$folder/$(basename "$part")")
    log "part $folder/$(basename "$part")"
  done
  if [ "${#parts[@]}" -eq 0 ]; then
    log "no part of seed $SEED under runs/*/controls/"
    exit 2
  fi
  "$IP" controls "$LOCAL" --merge "${parts[@]}"
  rc=$?
  log "merge exit $rc (2: refused, nothing written; the message names the part or the control)"
  [ "$rc" -eq 0 ] || exit "$rc"
  if [ -e "$STORED/controls.json" ]; then
    log "$RUN_PATH has controls.json now; this merge is discarded"
    exit 2
  fi
  cp "$LOCAL/controls.json" "$OUT/controls/"
  mkdir -p "$STORED/controls-parts" && cp -R "$WORK/parts/." "$STORED/controls-parts/"
  cp "$LOCAL/controls.json" "$STORED/controls.json"
  log "controls.json written to $RUN_PATH, its ${#parts[@]} parts to $RUN_PATH/controls-parts/"
  exit 0
fi

log "probe"
python3 docs/runbooks/host-probe.py --profile "$PROFILE" --work "$WORK" > "$OUT/probe.json"
log "probe exit $? (1: a profile requirement failed; see FAIL lines above)"
GPU=${IPROOFS_GPU:-$(python3 -c 'import json, sys
rows = json.load(open(sys.argv[1])).get("requirements") or []
found = [r["found"] for r in rows if r["id"] == "suggested_gpu_index"]
print(found[0] if found and found[0] is not None else 0)' "$OUT/probe.json" 2>/dev/null)}
GPU=${GPU:-0}
GPUS=""
case "$PROFILE" in
  serving-*|fidelity-*)  # RFC-0006 R6: every GPU of the profile is bound and counted
    # the count is in the name, <kind>-<gpu>x<count>[-hosted] (R6); the runner checks it
    count=$(printf '%s' "$PROFILE" | sed -E 's/^[a-z]+-[a-z0-9]+x([0-9]+).*$/\1/')
    all=0
    for ((i = 1; i < count; i++)); do all="$all,$i"; done
    GPUS=${IPROOFS_GPUS:-$all}
    GPU=${GPUS%%,*}
    ;;
esac
if [ -n "$GPUS" ]; then
  log "profile $PROFILE; bound GPUs $GPUS"
  GPU_ARGS=(--gpus "$GPUS")
else
  log "profile $PROFILE; bound GPU $GPU"
  GPU_ARGS=(--gpu "$GPU")
fi

# An image without uv (the ref-fidelity image, an engine image) gets the pinned release, its
# sha256 checked. The prover images and the pinned vLLM image ship their own (pinned by the image
# digest; job.log records `uv --version`), so nothing is downloaded for them.
UV_VERSION=0.11.18
UV_SHA256=588f3e360f69ce02b6982aa99f2240e803933a6b7e176ac01617830adf955add
if ! command -v uv >/dev/null; then
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
# the image's pip-interface settings (the vLLM image sets UV_OVERRIDE and UV_INDEX_STRATEGY for
# its own packages) never reach the harness install, which is the lock file's alone
if ! env -u UV_OVERRIDE -u UV_INDEX_STRATEGY -u UV_CONSTRAINT \
    uv sync --frozen --no-dev --extra gpu --extra fetch --extra prompts; then
  log "uv sync failed; stopping"
  exit 3
fi
"$IP" --version
if ! "$PY" -c 'import huggingface_hub, pynvml, tokenizers'; then
  log "an extra of the harness is missing (gpu, fetch or prompts); stopping"
  exit 3
fi
NGPU=$("$PY" -c 'import pynvml; pynvml.nvmlInit(); print(pynvml.nvmlDeviceGetCount())' 2>/dev/null)
NGPU=${NGPU:-0}
log "GPUs visible: $NGPU"
BOUND=0
if [ "$MODE" = controls ] && [ "$NGPU" -eq 0 ]; then
  log "a verifier host: no binding check and no self-test; verifier-side ids only"
else  # a GPU host: the binding check and the self-test, as for run and probe
  log "binding check: the CPUs iproofs run ${GPU_ARGS[*]} binds on $PROFILE"
  "$PY" - "${GPUS:-$GPU}" "$PROFILE" "$RELEASE" <<'EOF'
import sys
from pathlib import Path

from iproofs.model import load_reference
from iproofs.provenance import Host
from iproofs.runner import GpuEnvironment, ServingEnvironment
from iproofs.schema import SchemaRegistry

gpus, profile, release = [int(g) for g in sys.argv[1].split(",")], sys.argv[2], sys.argv[3]
root = Path.cwd()
found = load_reference(release, root, SchemaRegistry.from_tree(root / "schema")).profiles[profile]
n, host = found.cpu.logical_cpus_on_gpu_numa_node, Host(hosted=True)
serving = found.kind == "serving"
env = ServingEnvironment(gpus, host, n) if serving else GpuEnvironment(gpus[0], host, n)
binding = env.binding
print(f"binding: GPUs {gpus}, {len(binding.prover)} prover CPUs on NUMA node "
      f"{binding.mems[0]}, {len(binding.verifier)} verifier CPUs")
EOF
  BOUND=$?
  log "binding check exit $BOUND (not 0: every iproofs run on this GPU refuses to start)"

  log "hosted self-test (RFC-0011)"
  env -u HF_TOKEN "$IP" machine-record --hosted "${GPU_ARGS[@]}" --provider "$PROVIDER" --selftest \
    --results "$DEV" > "$OUT/selftest.json"
  log "self-test exit $?"
fi

[ "$MODE" = probe ] && exit 0
if [ "$MODE" = controls ]; then
  # RFC-0008 §Split suites: one part of the suite, against a copy of the stored run on this disk
  SEED=$(record_seed "$READ_FROM/controls-seed.json")
  # a prover-side id where no prove can run is refused here, before the copy and the weights
  if ! "$PY" - "$CSYSTEM" "$IDS" "$NGPU" <<'EOF'
import sys
from pathlib import Path

from iproofs.runner import control_suite
from iproofs.schema import SchemaRegistry

system, ids, ngpu = sys.argv[1], sys.argv[2].split(","), int(sys.argv[3])
root = Path.cwd()
sides = dict(control_suite(root, SchemaRegistry.from_tree(root / "schema"), system))
prover = [cid for cid in ids if sides.get(cid) == "prover"]
if prover and ngpu == 0:
    print(f"prover-side ids {', '.join(prover)} need a GPU flavor; this host has none")
    sys.exit(2)
EOF
  then
    log "refused before the copy"
    exit 2
  fi
  if [ "$NGPU" -gt 0 ] && [ "$BOUND" -ne 0 ]; then
    log "the binding check failed; stopping before the copy and the weights"
    exit 3
  fi
  RUN="$WORK/stored/dev-results/${RUN_PATH#*/dev-results/}"
  mkdir -p "$(dirname "$RUN")"
  log "copy $RUN_PATH from the bucket ($(du -sh "$READ_FROM" | cut -f1)), at most $(left) s"
  copy_start=$(date +%s)
  if ! timeout --kill-after=60 "$(left)" cp -R "$READ_FROM" "$RUN"; then
    log "the copy failed or reached the deadline; stopping"
    exit 3
  fi
  # the bucket's read speed is not documented: this line measures it, for the spend log
  log "copied $(du -sb "$RUN" | cut -f1) bytes in $(( $(date +%s) - copy_start )) s"
  extra=()
  if [ "$NGPU" -gt 0 ]; then  # the binding check passed (above)
    workload=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["workload"]["id"])' "$RUN/run.json")
    log "fetch-model $workload, at most $(left) s"
    if ! env -u HF_TOKEN timeout --kill-after=60 "$(left)" "$IP" fetch-model "$workload"; then
      log "fetch-model $workload failed or reached the deadline; stopping"
      exit 3
    fi
    extra=(--gpu "$GPU")
  fi
  log "controls $IDS, seed $SEED (from controls-seed.json), ${extra[*]:-no GPU}, at most $(left) s"
  # a progress line per control call that returns (control.call): what a rerun's timeout is
  # sized from if this job stops at its deadline (SPLIT-6)
  env -u HF_TOKEN timeout --kill-after=60 "$(left)" "$IP" controls "$RUN" --hosted "${extra[@]}" \
    --provider "$PROVIDER" --only "$IDS" --seed "$SEED"
  rc=$?
  # 0 the part is written; 2 refused (a prover-side id on a verifier host, a GPU other than the
  # run's, a part that exists); 124 or 137 stopped at the deadline: no part (SPLIT-6).
  log "controls exit $rc"
  mkdir -p "$OUT/controls"
  cp "$RUN"/controls-part-*.json "$OUT/controls/" 2>/dev/null || log "no part written"
  cp -R "$RUN/logs" "$OUT/controls/logs"
  exit "$rc"
fi
if [ "$MODE" = fidelity ]; then  # RFC-0018 FI-8: hf-job.sh fidelity RUNG, in the ref-fidelity image
  if [ $# -ne 1 ] || [ "$BOUND" -ne 0 ]; then
    log "usage: hf-job.sh fidelity RUNG (on a fidelity-* or serving-* profile; binding check must pass)"
    exit 2
  fi
  RUNG=$1
  RELEASE=v1.0
  log "level prompts $RUNG (needs levels/L1-beacon.json at this commit)"
  "$IP" level prompts "$RUNG" --out "$WORK/prompts" || { log "level prompts failed"; exit 3; }
  # the rung's reference and other model, at the revisions levels/L1.yaml pins; their files are
  # hashed into fidelity-run.json by the run (RFC-0018 FI-1, FI-2)
  fetch_args=()
  while IFS=$'\t' read -r what repo rev; do
    [ -n "$repo" ] || continue
    if [ "$rev" = None ]; then log "$what of $RUNG has no pinned revision in levels/L1.yaml"; exit 3; fi
    log "download $what: $repo at $rev, at most $(left) s"
    env -u HF_TOKEN timeout --kill-after=60 "$(left)" hfcli download "$repo" --revision "$rev" \
      --local-dir "$WORK/$what" >/dev/null || { log "download of $repo failed"; exit 3; }
    fetch_args+=("--$what-dir" "$WORK/$what")
  done < <("$PY" -c 'import sys
from pathlib import Path
from iproofs.level import load_level
level = load_level(Path.cwd())
rung = next(r for r in level.rungs if r.id == sys.argv[1])
src = getattr(rung.reference, "source", None)
if src is not None:
    print("reference", src.repo, src.revision, sep="\t")
for c in rung.controls:
    if c.recipe == "other_model":
        print("other-model", c.source.repo, c.source.revision, sep="\t")' "$RUNG")
  if [ "${#fetch_args[@]}" -eq 0 ] || [ "${fetch_args[0]}" != --reference-dir ]; then
    # the reference is the rung's serving record (RFC-0018 FI-1)
    record=$("$PY" -c 'import sys
from pathlib import Path
from iproofs.level import load_level
print(next(r for r in load_level(Path.cwd()).rungs if r.id == sys.argv[1]).serving)' "$RUNG")
    log "fetch-model --serving $record, at most $(left) s"
    timeout --kill-after=60 "$(left)" "$IP" fetch-model --serving "$record" || { log "fetch failed"; exit 3; }
  fi
  log "fidelity run $RUNG on GPUs ${GPUS:-$GPU}, at most $(left) s"
  env -u HF_TOKEN timeout --kill-after=60 "$(left)" "$IP" fidelity run --level L1 --rung "$RUNG" \
    --release "$RELEASE" --prompts-dir "$WORK/prompts" --gpus "${GPUS:-$GPU}" --hosted \
    --results "$DEV" --work "$WORK/fidelity-io" ${fetch_args[@]+"${fetch_args[@]}"}
  rc=$?
  log "fidelity run exit $rc"
  exit "$rc"
fi
if [ "$MODE" != run ] || [ $# -lt 2 ]; then
  log "usage: hf-job.sh probe | hf-job.sh run SYSTEM WORKLOAD:REPETITIONS[:controls][:keep-io][:high][:sizing=N][:from=DIR][:level=L1][:session=K][:ladder][:perturbed]..."
  log "       hf-job.sh seed|merge SYSTEM RUN_PATH | hf-job.sh controls SYSTEM RUN_PATH ID[,ID...]"
  exit 2
fi
if [ "$BOUND" -ne 0 ]; then
  log "the binding check failed; stopping before any weights are fetched"
  exit 3
fi
SYSTEM=$1
shift
case "$PROFILE" in
  serving-*)  # RFC-0006 PC-SHM before any weights: a tensor-parallel engine's workers share
    # /dev/shm (vLLM's message queues), and a small one fails only after the fetch
    need=$("$PY" -c 'import sys
from pathlib import Path
from iproofs.model import load_reference
from iproofs.schema import SchemaRegistry
root = Path.cwd()
p = load_reference(sys.argv[2], root, SchemaRegistry.from_tree(root / "schema")).profiles[sys.argv[1]]
print(int((getattr(p, "shm_gib_min", None) or 0) * 2**30) if p.gpu.count > 1 else 0)' \
      "$PROFILE" "$RELEASE" 2>/dev/null || echo unknown)
    have=$(df -B1 --output=size /dev/shm 2>/dev/null | tail -1 | tr -d ' ')
    log "PC-SHM: /dev/shm ${have:-unread} bytes, the profile needs ${need}"
    if [ "$need" = unknown ] || { [ "$need" -gt 0 ] && [ "${have:-0}" -lt "$need" ]; }; then
      log "/dev/shm below the serving profile's shm_gib_min, or unread; stopping before any weights"
      exit 3
    fi
    ;;
esac
image_args=()
if [ -n "${IPROOFS_DEV_IMAGE:-}" ]; then
  log "development install of $SYSTEM into $IPROOFS_DEV_IMAGE, from this checkout"
  if [ ! -f "systems/$SYSTEM/dev_install.py" ] \
    || ! python3 "systems/$SYSTEM/dev_install.py" "$IPROOFS_DEV_IMAGE" "${GPUS:-$GPU}"; then
    log "the development install or its engine check failed (or $SYSTEM has none); stopping before any weights"
    exit 3
  fi
  image_args=(--image "$IPROOFS_DEV_IMAGE" --keep-io)
fi
failed=0
FETCHED=" "   # serving records fetched and checked by an earlier step of this job
for step in "$@"; do
  IFS=: read -r workload reps opts <<< "$step"
  extra=()
  level_step=0
  IFS=: read -r -a flags <<< "${opts:-}"
  for flag in ${flags[@]+"${flags[@]}"}; do
    case "$flag" in
      controls) extra+=(--control-suite) ;;
      keep-io) extra+=(--keep-io) ;;
      high) extra+=(--load high) ;;
      sizing=*) extra+=(--sizing-batches "${flag#sizing=}") ;;
      from=*) extra+=(--prompts-from "${IPROOFS_UPLOAD_DIR:-/upload}/${flag#from=}") ;;
      level=*) extra+=(--level "${flag#level=}"); level_step=1; RELEASE=v1.0 ;;
      session=*) extra+=(--session "${flag#session=}") ;;
      ladder) extra+=(--load ladder) ;;
      perturbed) ;;  # handled below: the Model check's W' is committed before the run
      *) log "unknown step field $flag in $step"; exit 2 ;;
    esac
  done
  remaining=$(left)
  if [ "$remaining" -le 600 ]; then
    log "$remaining s left before the reserve; $workload not started"
    failed=1
    break
  fi
  # production serving runs the publisher's release its serving record pins (RFC-0015 SRV-6);
  # HF_TOKEN reaches that fetch only, for files the record takes from the publisher (Q7)
  record=$("$PY" -c 'import sys
from pathlib import Path
from iproofs.schema import SchemaRegistry
from iproofs.serving import record_for
from iproofs.workloads import reference_role
root = Path.cwd()
if reference_role(root, sys.argv[1]) == "serve":
    found = record_for(root, SchemaRegistry.from_tree(root / "schema"), sys.argv[2])
    print(found.id if found else "")' "$SYSTEM" "$workload" 2>/dev/null)
  if [ -n "$record" ] && [ -n "${IPROOFS_DEV_IMAGE:-}" ] && [ "${FETCHED#* "$record" }" = "$FETCHED" ]; then
    # the engine's tokenizer and processor load from the record's files without the weights,
    # as the adapter is dropped: a file the engine cannot read stops the job before the fetch
    small="$WORK/no-weights/$record"
    log "tokenizer check of $record, before its weights"
    if ! timeout --kill-after=60 600 "$IP" fetch-model --serving "$record" --no-weights "$small" \
      || ! python3 "systems/$SYSTEM/dev_install.py" --tokenizer-check "$small"; then
      log "the tokenizer check of $record failed; next step, no weights fetched"
      failed=1
      continue
    fi
  fi
  if [ -n "$record" ] && [ "${FETCHED#* "$record" }" != "$FETCHED" ]; then
    # fetched and checked (SM-2) by an earlier step of this job; the run rehashes it at its
    # start (RFC-0014), so a second check here would read every byte once more
    log "fetch-model $record: done by an earlier step; the run rehashes it"
  else
    fetch=(env -u HF_TOKEN timeout --kill-after=60 "$remaining" "$IP" fetch-model "$workload")
    [ -n "$record" ] && fetch=(timeout --kill-after=60 "$remaining" "$IP" fetch-model --serving "$record")
    log "fetch-model ${record:-$workload}, at most $remaining s"
    if ! "${fetch[@]}"; then
      log "fetch-model $workload failed or reached the deadline; next step"
      failed=1
      continue
    fi
    [ -n "$record" ] && FETCHED="$FETCHED$record "
  fi
  remaining=$(left)
  if [ "$remaining" -le 600 ]; then
    log "$remaining s left before the reserve; $workload not started"
    failed=1
    break
  fi
  if has_opt "${opts:-}" perturbed; then  # RFC-0018 CH-2: commit W' on this host, for C3 and P1
    level_id=L1
    for flag in ${flags[@]+"${flags[@]}"}; do case "$flag" in level=*) level_id=${flag#level=} ;; esac; done
    log "prepare-perturbed $SYSTEM $workload (level $level_id), at most $(left) s"
    if ! env -u HF_TOKEN timeout --kill-after=60 "$(left)" "$IP" controls --prepare-perturbed "$workload" \
      --system "$SYSTEM" --profile "$PROFILE" --hosted --gpu "$GPU" --level "$level_id" \
      --results "$DEV" ${image_args[@]+"${image_args[@]:0:2}"}; then
      log "prepare-perturbed failed; the run goes on and records C3 and P1 not_applicable"
    fi
  fi
  reps_args=(--repetitions "${reps:-1}")
  if [ "$level_step" -eq 1 ]; then  # one run is one session of the level (RFC-0018 SE-1)
    [ "${reps:-1}" = 1 ] || { log "a level step runs one session: REPETITIONS must be 1 in $step"; exit 2; }
    reps_args=()
  fi
  log "run $SYSTEM $workload x${reps:-1} ${extra[*]:-} ${image_args[*]:-}, at most $remaining s"
  env -u HF_TOKEN timeout --kill-after=60 "$remaining" "$IP" run --system "$SYSTEM" \
    --workload "$workload" --profile "$PROFILE" --hosted "${GPU_ARGS[@]}" --provider "$PROVIDER" \
    ${reps_args[@]+"${reps_args[@]}"} --allow-nonconforming --results "$DEV" \
    ${extra[@]+"${extra[@]}"} ${image_args[@]+"${image_args[@]}"}  # empty arrays under bash 3.2 too
  rc=$?
  # 0 all repetitions completed; 4 a repetition was recorded as failed; 124 or 137 stopped at
  # the job's deadline: its staging directory is uploaded without io/, the scratch directories
  # and the commitment store (prune); other: a harness error.
  log "run $SYSTEM $workload exit $rc"
  if has_opt "${opts:-}" keep-io; then  # what the upload will copy: proofs, state, commitment
    for kept in "$DEV/$RELEASE/$SYSTEM"/*/io "$DEV/$RELEASE/$SYSTEM"/*/commitment; do
      [ -d "$kept" ] && log "keep-io: $(du -sh "$kept" | cut -f1) $(basename "$(dirname "$kept")")/$(basename "$kept")"
    done
  fi
  [ "$rc" -eq 0 ] || failed=1
done
exit "$failed"
