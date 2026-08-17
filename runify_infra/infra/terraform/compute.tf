# Ubuntu 22.04 LTS 최신 이미지
data "google_compute_image" "ubuntu" {
  family  = "ubuntu-2204-lts"
  project = "ubuntu-os-cloud"
}

resource "google_compute_instance" "backend_vm" {
  name         = "backend-vm"
  machine_type = "e2-medium"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = data.google_compute_image.ubuntu.self_link
      size  = 30
    }
  }

  network_interface {
    network    = google_compute_network.runify_vpc.id
    subnetwork = google_compute_subnetwork.runify_subnet.id
    access_config {
      # 외부 IP 할당
    }
  }

  service_account {
    email  = google_service_account.vm_sa.email
    scopes = ["cloud-platform"]
  }

  tags = ["backend"]
}

resource "google_compute_instance" "kafka_vm" {
  name         = "kafka-vm"
  machine_type = "e2-medium"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = data.google_compute_image.ubuntu.self_link
      size  = 50
    }
  }

  network_interface {
    network    = google_compute_network.runify_vpc.id
    subnetwork = google_compute_subnetwork.runify_subnet.id
    # 외부 IP 없음 (IAP 통해 접속)
  }

  service_account {
    email  = google_service_account.vm_sa.email
    scopes = ["cloud-platform"]
  }
}

resource "google_compute_instance" "route_worker_vm" {
  name         = "route-worker-vm"
  machine_type = "e2-medium"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = data.google_compute_image.ubuntu.self_link
      size  = 50
    }
  }

  network_interface {
    network    = google_compute_network.runify_vpc.id
    subnetwork = google_compute_subnetwork.runify_subnet.id
    # 외부 IP 없음 (IAP 통해 접속)
  }

  service_account {
    email  = google_service_account.vm_sa.email
    scopes = ["cloud-platform"]
  }
}
