#!/usr/bin/env bash
# One development job of the harness on Hugging Face Jobs, inside a container the provider
# started from a pinned adapter image (docs/runbooks/hf-jobs.md, RFC-0006 §Hosted execution).
# The job's command clones this repository at IPROOFS_COMMIT and runs this script from it:
#
#   hf-job.sh probe                          host probe, harness install, binding check, self-test
#   hf-job.sh run SYSTEM STEP [STEP...]      the same, then each STEP in order
#   hf-job.sh controls SYSTEM RUN_PATH SEED ID[,ID...]
#                                            the same, then one part of a run's control suite
#
# A STEP is WORKLOAD:REPETITIONS with options after further colons: `controls` (the control
# suite, in this job) and `keep-io` (the run directory keeps io/, with its proofs, and its
# commitment store, and both are uploaded, so that `controls` jobs can run from the bucket),
# for example `fp-maverick-w1024-b1:2:controls` or `sash-l31-8b-c1024:1:keep-io`. `keep-io` is
# refused for flashprove: its io/ holds a copy of the weights and its commitment store the
# prover's secret key. Every run is a development run on prover-h200-hosted
# (--allow-nonconforming until RFC-0006 Q5 pins the driver), written outside the checkout and
# never copied into results/ (POL-4).
#
# `controls` (RFC-0008 §Split suites) copies the run directory runs/<UTC>-<label>/dev-results/
# <release>/SYSTEM/<run id> (RUN_PATH) from the mounted bucket, runs `iproofs controls --hosted
# --only ID[,ID...] --seed SEED` against it, and uploads the part file and the logs under
# controls/. With a GPU the job binds it and fetches the weights (prover-side ids); without one
# it is a verifier host, which runs verifier-side ids only.
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
    [ -d "$OUT/controls" ] && cp -R "$OUT/controls" "$dest/"
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
  IPROOFS_FOLDER="$folder" IPROOFS_OUT="$OUT" $py - <<'EOF' || log "upload: failed"
import os
from huggingface_hub import HfApi

api = HfApi()  # reads HF_TOKEN from the environment; it is never printed
repo, out, folder = os.environ["IPROOFS_UPLOAD"], os.environ["IPROOFS_OUT"], os.environ["IPROOFS_FOLDER"]
message = "development run (docs/runbooks/hf-jobs.md)"
# The dataset exists already (hf-jobs.md stage 0): a token scoped to it cannot create it.
# Two commits: the log, probe and self-test first, then the run directories.
api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=out, path_in_repo=folder,
                  allow_patterns=["*.json", "job.log", "controls/**"], commit_message=message)
api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=out, path_in_repo=folder,
                  allow_patterns=["dev-results/**"],
                  ignore_patterns=["**/.staging-*/io/**", "**/.staging-*/prover-ro/**",
                                   "**/.staging-*/verify/**", "**/.staging-*/controls-io/**",
                                   "**/.staging-*/commitment/**"],
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
    # a kept SASH run holds its 44.6 GB proof (the H100 run's manifest); the bucket's write speed
    # is not documented: 3,600 s is enough at 12.4 MB/s or more, an assumption
    RESERVE=3600
  done
fi
if [ "$MODE" = controls ]; then
  if [ $# -ne 4 ]; then
    log "usage: hf-job.sh controls SYSTEM RUN_PATH SEED ID[,ID...]"
    exit 2
  fi
  CSYSTEM=$1 RUN_PATH=${2%/} SEED=$3 IDS=$4
  if [ -z "${IPROOFS_UPLOAD_DIR:-}" ]; then
    log "controls reads the run from the mounted bucket: set IPROOFS_UPLOAD_DIR"
    exit 2
  fi
  case "$RUN_PATH" in
    runs/*/dev-results/*/"$CSYSTEM"/*) ;;
    *) log "RUN_PATH must be runs/<folder>/dev-results/<release>/$CSYSTEM/<run id>"; exit 2 ;;
  esac
  STORED="$IPROOFS_UPLOAD_DIR/$RUN_PATH"
  if [ ! -f "$STORED/run.json" ] || [ ! -d "$STORED/io/proofs" ] || [ ! -d "$STORED/commitment" ]; then
    log "no kept run at $RUN_PATH: it needs run.json, io/proofs and commitment/ (a run made with keep-io)"
    exit 2
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
NGPU=$("$PY" -c 'import pynvml; pynvml.nvmlInit(); print(pynvml.nvmlDeviceGetCount())' 2>/dev/null)
NGPU=${NGPU:-0}
log "GPUs visible: $NGPU"
BOUND=0
if [ "$MODE" = controls ] && [ "$NGPU" -eq 0 ]; then
  log "a verifier host: no binding check and no self-test; verifier-side ids only"
else  # a GPU host: the binding check and the self-test, as for run and probe
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
fi

[ "$MODE" = probe ] && exit 0
if [ "$MODE" = controls ]; then
  # RFC-0008 §Split suites: one part of the suite, against a copy of the stored run on this disk
  RUN="$WORK/stored/dev-results/${RUN_PATH#*/dev-results/}"
  mkdir -p "$(dirname "$RUN")"
  log "copy $RUN_PATH from the bucket ($(du -sh "$STORED" | cut -f1)), at most $(left) s"
  if ! timeout --kill-after=60 "$(left)" cp -R "$STORED" "$RUN"; then
    log "the copy failed or reached the deadline; stopping"
    exit 3
  fi
  extra=()
  if [ "$NGPU" -gt 0 ]; then
    if [ "$BOUND" -ne 0 ]; then
      log "the binding check failed; stopping before any weights are fetched"
      exit 3
    fi
    workload=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["workload"]["id"])' "$RUN/run.json")
    log "fetch-model $workload, at most $(left) s"
    if ! env -u HF_TOKEN timeout --kill-after=60 "$(left)" "$IP" fetch-model "$workload"; then
      log "fetch-model $workload failed or reached the deadline; stopping"
      exit 3
    fi
    extra=(--gpu "$GPU")
  fi
  log "controls $IDS, seed $SEED, ${extra[*]:-no GPU}, at most $(left) s"
  env -u HF_TOKEN timeout --kill-after=60 "$(left)" "$IP" controls "$RUN" --hosted "${extra[@]}" \
    --only "$IDS" --seed "$SEED"
  rc=$?
  # 0 the part is written; 2 refused (a prover-side id on a verifier host, an unknown id, a part
  # that exists); 124 or 137 stopped at the deadline: no part, the controls run again (SPLIT-6).
  log "controls exit $rc"
  mkdir -p "$OUT/controls"
  cp "$RUN"/controls-part-*.json "$OUT/controls/" 2>/dev/null || log "no part written"
  cp -R "$RUN/logs" "$OUT/controls/logs"
  exit "$rc"
fi
if [ "$MODE" != run ] || [ $# -lt 2 ]; then
  log "usage: hf-job.sh probe | hf-job.sh run SYSTEM WORKLOAD:REPETITIONS[:controls][:keep-io]..."
  log "       hf-job.sh controls SYSTEM RUN_PATH SEED ID[,ID...]"
  exit 2
fi
if [ "$BOUND" -ne 0 ]; then
  log "the binding check failed; stopping before any weights are fetched"
  exit 3
fi
SYSTEM=$1
shift
failed=0
for step in "$@"; do
  IFS=: read -r workload reps opts <<< "$step"
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
  has_opt "${opts:-}" controls && extra+=(--control-suite)
  has_opt "${opts:-}" keep-io && extra+=(--keep-io)
  log "run $SYSTEM $workload x${reps:-1} ${extra[*]:-}, at most $remaining s"
  env -u HF_TOKEN timeout --kill-after=60 "$remaining" "$IP" run --system "$SYSTEM" \
    --workload "$workload" --profile "$PROFILE" --hosted --gpu "$GPU" --provider "$PROVIDER" \
    --repetitions "${reps:-1}" --allow-nonconforming --results "$DEV" "${extra[@]}"
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
