# VM 전용 서비스 계정
resource "google_service_account" "vm_sa" {
  account_id   = "runify-vm-sa"
  display_name = "Service Account for Runify VMs"
}

# Artifact Registry Reader 역할 부여 (VM들이 Docker 이미지를 Pull 받을 수 있게 함)
resource "google_artifact_registry_repository_iam_member" "vm_ar_reader" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.runify_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.vm_sa.email}"
}
