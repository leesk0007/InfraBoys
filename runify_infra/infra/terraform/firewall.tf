# 내부 통신 허용 (VPC 내부 리소스끼리)
resource "google_compute_firewall" "allow_internal" {
  name    = "runify-allow-internal"
  network = google_compute_network.runify_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "icmp"
  }

  source_ranges = ["10.0.1.0/24"]
}

# IAP를 통한 SSH 통신 허용 (외부에서 직접 22번 포트 노출 방지)
resource "google_compute_firewall" "allow_iap_ssh" {
  name    = "runify-allow-iap-ssh"
  network = google_compute_network.runify_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"] # GCP IAP 대역
}

# Backend API 접속을 위한 외부 HTTP(8080) 허용
resource "google_compute_firewall" "allow_backend_api" {
  name    = "runify-allow-backend-api"
  network = google_compute_network.runify_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["backend"]
}
