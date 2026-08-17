resource "google_artifact_registry_repository" "runify_repo" {
  location      = var.region
  repository_id = "runify-repo"
  description   = "Docker repository for Runify Backend and Worker"
  format        = "DOCKER"
}
