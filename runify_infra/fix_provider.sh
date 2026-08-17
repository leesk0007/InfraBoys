export PROJECT_ID="project-711a7776-5c81-4794-998"
export GITHUB_REPO="KozzilzzilE/Runify_infra"

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
    --project=$PROJECT_ID \
    --location="global" \
    --workload-identity-pool="github-pool" \
    --display-name="GitHub provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository == '${GITHUB_REPO}'" \
    --issuer-uri="https://token.actions.githubusercontent.com" || echo "Failed to create"

gcloud iam workload-identity-pools providers describe "github-provider" \
    --project=$PROJECT_ID --location="global" --workload-identity-pool="github-pool" --format="value(name)"
