# 1. 환경 변수 설정
export PROJECT_ID="project-711a7776-5c81-4794-998"
export GCS_BUCKET="runify-tf-state-bucket"
export GITHUB_REPO="KozzilzzilE/Runify_infra"

gcloud config set project $PROJECT_ID

# 2. 필수 API 활성화
echo "✅ API 활성화 중..."
gcloud services enable compute.googleapis.com \
    iam.googleapis.com \
    cloudresourcemanager.googleapis.com \
    artifactregistry.googleapis.com \
    iamcredentials.googleapis.com

# 3. 테라폼 상태 저장을 위한 GCS 버킷 생성 (이미 있으면 무시)
echo "✅ GCS 버킷 생성 중..."
gcloud storage buckets create gs://$GCS_BUCKET --location=asia-northeast3 || echo "버킷이 이미 존재합니다. 넘어갑니다."

# 4. Terraform 실행 전용 서비스 계정 생성 (이미 있으면 무시)
echo "✅ 서비스 계정 생성 중..."
gcloud iam service-accounts create tf-executor \
    --display-name="Terraform Executor for GitHub Actions" || echo "서비스 계정이 이미 존재합니다. 넘어갑니다."

# 서비스 계정에 권한(Project Editor) 부여
echo "✅ 서비스 계정에 Editor 권한 부여 중..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:tf-executor@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/editor"

# 5. WIF (Workload Identity Pool & Provider) 생성 (이미 있으면 무시)
echo "✅ WIF Pool 생성 중..."
gcloud iam workload-identity-pools create "github-pool" \
    --project=$PROJECT_ID \
    --location="global" \
    --display-name="GitHub Actions Pool" || echo "Pool이 이미 존재합니다. 넘어갑니다."

echo "✅ WIF Provider 생성 중..."
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
    --project=$PROJECT_ID \
    --location="global" \
    --workload-identity-pool="github-pool" \
    --display-name="GitHub provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository == '${GITHUB_REPO}'" \
    --issuer-uri="https://token.actions.githubusercontent.com" || echo "Provider가 이미 존재합니다. 넘어갑니다."

# 6. 특정 GitHub Repository만 접근할 수 있도록 WIF 바인딩
echo "✅ GitHub 레포지토리 바인딩 중..."
export WORKLOAD_IDENTITY_POOL_ID=$(gcloud iam workload-identity-pools describe "github-pool" \
    --project=$PROJECT_ID --location="global" --format="value(name)")

gcloud iam service-accounts add-iam-policy-binding "tf-executor@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project=$PROJECT_ID \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/${WORKLOAD_IDENTITY_POOL_ID}/attribute.repository/${GITHUB_REPO}"

# 7. GitHub Secrets에 넣을 값 출력
echo -e "\n============================================="
echo "✅ 작업 완료! 아래 두 값을 복사해서 GitHub Secrets에 등록하세요."
echo "============================================="
echo "GCP_WORKLOAD_IDENTITY_PROVIDER:"
gcloud iam workload-identity-pools providers describe "github-provider" \
    --project=$PROJECT_ID --location="global" --workload-identity-pool="github-pool" --format="value(name)"
echo ""
echo "GCP_SERVICE_ACCOUNT:"
echo "tf-executor@${PROJECT_ID}.iam.gserviceaccount.com"
echo "============================================="
