resource "google_compute_network" "runify_vpc" {
  name                    = "runify-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "runify_subnet" {
  name          = "runify-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.runify_vpc.id
}
