provider "google" {
  credentials = var.credentials_json
  project     = var.project_id
  region      = var.region
  zone        = var.zone
}

resource "google_compute_instance" "vm" {
  name         = var.name
  machine_type = var.machine_type
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = var.image
    }
  }

  network_interface {
    network = "default"
    access_config {
      // Ephemeral IP
    }
  }
}

output "instance_id" {
  value = google_compute_instance.vm.id
}

output "name" {
  value = google_compute_instance.vm.name
}

output "external_ip" {
  value = google_compute_instance.vm.network_interface[0].access_config[0].nat_ip
}

output "internal_ip" {
  value = google_compute_instance.vm.network_interface[0].network_ip
}

output "status" {
  value = google_compute_instance.vm.current_status
}
