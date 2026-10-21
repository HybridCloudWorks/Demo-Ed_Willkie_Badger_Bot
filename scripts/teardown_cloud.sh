#!/usr/bin/env bash
# Remove everything this project created in Google Cloud and GitHub, and prove
# that nothing else changed. The repository stays as it is, so a redeploy is:
#
#     bash scripts/setup_github_deployer.sh      # identity + repo variables
#     gh workflow run deploy-cloud-run.yml       # or push to main
#
# The Cloud Run URL is derived from the service name, project number and
# region, so the recreated service gets the same address the slide deck and QR
# codes already carry.
#
#     bash scripts/teardown_cloud.sh            # plan only: show what exists, change nothing
#     bash scripts/teardown_cloud.sh --apply    # delete, then validate
#
# Needs: gcloud signed in as a project Owner, gh signed in with repo admin.
#
# What is removed (and only this):
#   Cloud Run     service willkie-badger-ai (us-central1)
#   Artifact Reg. package willkie-badger-ai inside the shared cloud-run-source-deploy repo
#   Cloud Storage objects under services/willkie-badger-ai/ in the shared run-sources bucket
#   IAM           service account github-deployer, its project role bindings, and its
#                 serviceAccountUser binding on the runtime service account
#   WIF           workload identity pool "github" (with its provider "github")
#   GitHub        the four GCP_* repository variables
# What is left alone on purpose: enabled APIs (shared), the Artifact Registry
# repository and the run-sources bucket themselves (shared with other services),
# the runtime service account and its roles, every other Cloud Run service,
# service account, pool and bucket, and Cloud Build history (not deletable).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-simplysoph-66c78}"
REGION="${REGION:-us-central1}"
REPO="${REPO:-HybridCloudWorks/Demo-Ed_Willkie_Badger_Bot}"
SERVICE="willkie-badger-ai"
SA_NAME="github-deployer"
POOL="github"
AR_REPO="cloud-run-source-deploy"
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format 'value(projectNumber)')
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
RUNTIME_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
SOURCES="gs://run-sources-$PROJECT_ID-$REGION/services/$SERVICE/"
DEPLOYER_ROLES=(roles/run.admin roles/cloudbuild.builds.editor roles/artifactregistry.writer
                roles/storage.admin roles/serviceusage.serviceUsageConsumer)
GH_VARS=(GCP_PROJECT_ID GCP_REGION GCP_WORKLOAD_IDENTITY_PROVIDER GCP_DEPLOYER_SA)

say()  { printf '%s\n' "$*"; }
ok()   { printf '  [ok]   %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; FAILED=1; }
FAILED=0

# ---------------------------------------------------------------------------
# Inventory. Everything that is NOT a target must look identical before and
# after; everything that IS a target must be present before and gone after.
# ---------------------------------------------------------------------------
inventory() {
  {
    echo "## run services";      gcloud run services list --project "$PROJECT_ID" --format 'value(metadata.name)' | sort
    echo "## service accounts";  gcloud iam service-accounts list --project "$PROJECT_ID" --format 'value(email)' | sort
    echo "## wif pools";         gcloud iam workload-identity-pools list --project "$PROJECT_ID" --location global --format 'value(name)' | sort
    echo "## ar repos";          gcloud artifacts repositories list --project "$PROJECT_ID" --location "$REGION" --format 'value(name)' | sort
    echo "## ar packages";       gcloud artifacts packages list --project "$PROJECT_ID" --location "$REGION" --repository "$AR_REPO" --format 'value(name)' | sort
    echo "## buckets";           gcloud storage ls --project "$PROJECT_ID" | sort
    echo "## run-sources prefixes"; gcloud storage ls "gs://run-sources-$PROJECT_ID-$REGION/services/" 2>/dev/null | sort
    echo "## runtime sa roles";  gcloud projects get-iam-policy "$PROJECT_ID" --flatten 'bindings[].members' \
                                   --filter "bindings.members:$RUNTIME_SA" --format 'value(bindings.role)' | sort
    echo "## enabled apis";      gcloud services list --enabled --project "$PROJECT_ID" --format 'value(config.name)' | sort
    echo "## github variables";  gh variable list -R "$REPO" --json name -q '.[].name' | sort
  } 2>/dev/null
}

# Lines in the inventory that belong to the targets; everything else must not change.
is_target_line() {
  case "$1" in
    "$SERVICE"|"$SA_EMAIL"|*"/workloadIdentityPools/$POOL"|"$SOURCES"|GCP_PROJECT_ID|GCP_REGION|GCP_WORKLOAD_IDENTITY_PROVIDER|GCP_DEPLOYER_SA) return 0 ;;
    *) return 1 ;;
  esac
}
non_targets() { while IFS= read -r line; do is_target_line "$line" || printf '%s\n' "$line"; done; }

exists_service()  { gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" >/dev/null 2>&1; }
exists_package()  { gcloud artifacts packages describe "$SERVICE" --project "$PROJECT_ID" --location "$REGION" --repository "$AR_REPO" >/dev/null 2>&1; }
exists_sources()  { gcloud storage ls "$SOURCES" >/dev/null 2>&1; }
exists_sa()       { gcloud iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1; }
exists_pool()     { [[ "$(gcloud iam workload-identity-pools describe "$POOL" --project "$PROJECT_ID" --location global --format 'value(state)' 2>/dev/null)" == "ACTIVE" ]]; }
exists_var()      { gh variable list -R "$REPO" --json name -q '.[].name' | grep -qx "$1"; }
deployer_roles()  { gcloud projects get-iam-policy "$PROJECT_ID" --flatten 'bindings[].members' --filter "bindings.members:$SA_EMAIL" --format 'value(bindings.role)' 2>/dev/null; }
runtime_binding() { gcloud iam service-accounts get-iam-policy "$RUNTIME_SA" --project "$PROJECT_ID" --format json 2>/dev/null | grep -c "serviceAccount:$SA_EMAIL" || true; }

say "Project $PROJECT_ID ($PROJECT_NUMBER), region $REGION, repo $REPO"
if [[ $APPLY == 1 ]]; then say "Mode: APPLY"; else say "Mode: PLAN (read-only; pass --apply to delete)"; fi
say
say "Resources this script owns:"
exists_service && say "  present  Cloud Run service $SERVICE"            || say "  absent   Cloud Run service $SERVICE"
exists_package && say "  present  Artifact Registry package $AR_REPO/$SERVICE" || say "  absent   Artifact Registry package $AR_REPO/$SERVICE"
exists_sources && say "  present  source uploads $SOURCES"               || say "  absent   source uploads $SOURCES"
exists_sa      && say "  present  service account $SA_EMAIL (roles: $(deployer_roles | tr '\n' ' '))" || say "  absent   service account $SA_EMAIL"
[[ "$(runtime_binding)" != "0" ]] && say "  present  serviceAccountUser binding on $RUNTIME_SA" || say "  absent   serviceAccountUser binding on $RUNTIME_SA"
exists_pool    && say "  present  workload identity pool $POOL"           || say "  absent   workload identity pool $POOL"
for v in "${GH_VARS[@]}"; do exists_var "$v" && say "  present  GitHub variable $v" || say "  absent   GitHub variable $v"; done
say

if [[ $APPLY == 0 ]]; then
  say "Nothing changed. Re-run with --apply to remove the items marked present."
  exit 0
fi

BEFORE=$(mktemp); AFTER=$(mktemp)
inventory > "$BEFORE"

say "Removing..."
if exists_service; then
  gcloud run services delete "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --quiet && ok "Cloud Run service deleted"
fi
if exists_package; then
  gcloud artifacts packages delete "$SERVICE" --project "$PROJECT_ID" --location "$REGION" --repository "$AR_REPO" --quiet && ok "container images deleted"
fi
if exists_sources; then
  gcloud storage rm -r "$SOURCES" --quiet && ok "source uploads deleted"
fi
if exists_sa; then
  for role in $(deployer_roles); do
    gcloud projects remove-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$SA_EMAIL" --role "$role" --quiet >/dev/null && ok "project role $role removed"
  done
  if [[ "$(runtime_binding)" != "0" ]]; then
    gcloud iam service-accounts remove-iam-policy-binding "$RUNTIME_SA" --project "$PROJECT_ID" \
      --member "serviceAccount:$SA_EMAIL" --role roles/iam.serviceAccountUser --quiet >/dev/null && ok "runtime SA binding removed"
  fi
  gcloud iam service-accounts delete "$SA_EMAIL" --project "$PROJECT_ID" --quiet && ok "service account deleted"
fi
if exists_pool; then
  # Pools are soft-deleted for 30 days; setup_github_deployer.sh undeletes it if you redeploy within that window.
  gcloud iam workload-identity-pools delete "$POOL" --project "$PROJECT_ID" --location global --quiet && ok "workload identity pool deleted"
fi
for v in "${GH_VARS[@]}"; do
  exists_var "$v" && gh variable delete "$v" -R "$REPO" && ok "GitHub variable $v deleted"
done

say
say "Validating..."
inventory > "$AFTER"

# 1. Every target is gone.
exists_service && bad "Cloud Run service still exists" || ok "Cloud Run service gone"
exists_package && bad "Artifact Registry package still exists" || ok "container images gone"
exists_sources && bad "source uploads still exist" || ok "source uploads gone"
exists_sa && bad "service account still exists" || ok "service account gone"
[[ -n "$(deployer_roles)" ]] && bad "project still has role bindings for $SA_EMAIL" || ok "no project role bindings left for the deployer"
[[ "$(runtime_binding)" != "0" ]] && bad "runtime SA still lists the deployer" || ok "runtime SA binding gone"
exists_pool && bad "workload identity pool still active" || ok "workload identity pool gone"
for v in "${GH_VARS[@]}"; do exists_var "$v" && bad "GitHub variable $v still exists" || ok "GitHub variable $v gone"; done

# 2. Nothing else changed: the non-target inventory is byte-for-byte identical.
if diff <(non_targets < "$BEFORE") <(non_targets < "$AFTER") >/dev/null; then
  ok "everything else is unchanged ($(non_targets < "$AFTER" | grep -vc '^## ') items checked: services, service accounts, pools, repositories, buckets, runtime roles, APIs, variables)"
else
  bad "something outside the target list changed:"
  diff <(non_targets < "$BEFORE") <(non_targets < "$AFTER") || true
fi
rm -f "$BEFORE" "$AFTER"

say
if [[ $FAILED == 0 ]]; then
  say "Teardown complete and verified. To bring it back: bash scripts/setup_github_deployer.sh, then run the Deploy to Cloud Run workflow."
else
  say "Teardown finished with problems; see [FAIL] lines above."
  exit 1
fi
