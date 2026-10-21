#!/usr/bin/env bash
# One-time setup so .github/workflows/deploy-cloud-run.yml can deploy without a
# stored key (Workload Identity Federation). Safe to re-run: every step is
# idempotent or tolerates "already exists".
#
# Needs: gcloud signed in as a project Owner, gh signed in with repo admin.
#   bash scripts/setup_github_deployer.sh
#
# What it creates in the Google Cloud project:
#   - service account github-deployer with the roles Cloud Run source deploys need
#   - workload identity pool "github" + OIDC provider "github" limited to this repo
#   - permission for this repo's GitHub Actions jobs to act as github-deployer
# What it sets on GitHub: the four repository variables the workflow reads.
# The reverse of this script is scripts/teardown_cloud.sh.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-simplysoph-66c78}"
REGION="${REGION:-us-central1}"
REPO="${REPO:-HybridCloudWorks/Demo-Ed_Willkie_Badger_Bot}"
SA_NAME="github-deployer"
POOL="github"
PROVIDER="github"

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format 'value(projectNumber)')
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
RUNTIME_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
REPO_ID=$(gh api "repos/$REPO" --jq '.id')
OWNER_ID=$(gh api "repos/$REPO" --jq '.owner.id')

echo "Project $PROJECT_ID ($PROJECT_NUMBER), repo $REPO (id $REPO_ID, owner id $OWNER_ID)"

gcloud services enable sts.googleapis.com iamcredentials.googleapis.com run.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com --project "$PROJECT_ID"

# 1. Deployer service account.
gcloud iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1 ||
  gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT_ID" \
    --display-name "GitHub Actions deployer (Demo-Ed_Willkie_Badger_Bot)"

# 2. Roles a `gcloud run deploy --source` needs. --condition=None: the project policy
#    already holds conditional bindings, which gcloud otherwise refuses non-interactively. Cloud Run, Cloud Build, the
#    Artifact Registry repo it writes to, the source-upload bucket, and the right
#    to run the service as the runtime service account.
for role in roles/run.admin roles/cloudbuild.builds.editor roles/artifactregistry.writer \
            roles/storage.admin roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --quiet --condition=None \
    --member "serviceAccount:$SA_EMAIL" --role "$role" >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --project "$PROJECT_ID" --quiet --condition=None \
  --member "serviceAccount:$SA_EMAIL" --role roles/iam.serviceAccountUser >/dev/null

# 3. Identity pool + OIDC provider trusting only this repository. A pool or
#    provider removed by scripts/teardown_cloud.sh stays soft-deleted for 30
#    days; within that window it must be undeleted, not recreated.
pool_state=$(gcloud iam workload-identity-pools describe "$POOL" --project "$PROJECT_ID" --location global --format 'value(state)' 2>/dev/null || true)
case "$pool_state" in
  ACTIVE)  ;;
  DELETED) gcloud iam workload-identity-pools undelete "$POOL" --project "$PROJECT_ID" --location global --quiet ;;
  *)       gcloud iam workload-identity-pools create "$POOL" --project "$PROJECT_ID" --location global --display-name "GitHub (HybridCloudWorks)" ;;
esac
provider_state=$(gcloud iam workload-identity-pools providers describe "$PROVIDER" --project "$PROJECT_ID" --location global --workload-identity-pool "$POOL" --format 'value(state)' 2>/dev/null || true)
if [[ "$provider_state" == "DELETED" ]]; then
  gcloud iam workload-identity-pools providers undelete "$PROVIDER" --project "$PROJECT_ID" --location global --workload-identity-pool "$POOL" --quiet
elif [[ "$provider_state" != "ACTIVE" ]]; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --project "$PROJECT_ID" \
    --location global --workload-identity-pool "$POOL" --display-name "GitHub Actions OIDC" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository_id == '$REPO_ID' && assertion.repository_owner_id == '$OWNER_ID'"
fi

# 4. Let this repo's jobs impersonate the deployer.
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" --project "$PROJECT_ID" --quiet --condition=None \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository_id/$REPO_ID" >/dev/null

# 5. Repository variables (no secrets).
PROVIDER_NAME="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER"
gh variable set GCP_PROJECT_ID -R "$REPO" -b "$PROJECT_ID"
gh variable set GCP_REGION -R "$REPO" -b "$REGION"
gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER -R "$REPO" -b "$PROVIDER_NAME"
gh variable set GCP_DEPLOYER_SA -R "$REPO" -b "$SA_EMAIL"

echo "Done. IAM takes about a minute to propagate; then push to main or run: gh workflow run deploy-cloud-run.yml"
