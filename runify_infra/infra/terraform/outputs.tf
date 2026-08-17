output "backend_public_ip" {
  description = "Public IP of the Backend VM"
  value       = google_compute_instance.backend_vm.network_interface[0].access_config[0].nat_ip
}

output "artifact_registry_url" {
  description = "URL of the Artifact Registry"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.runify_repo.name}"
}
