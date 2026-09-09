# VPC + private services access so Cloud SQL can use a private IP, plus a
# Serverless VPC Access connector so Cloud Run can reach it.

resource "google_compute_network" "vpc" {
  project                 = var.project_id
  name                    = "${var.name}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  project       = var.project_id
  name          = "${var.name}-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.10.0.0/24"
}

# Reserved range for the private services (Cloud SQL) VPC peering.
resource "google_compute_global_address" "private_services_range" {
  project       = var.project_id
  name          = "${var.name}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services_range.name]
}

# Serverless VPC Access connector so Cloud Run can reach the private-IP Cloud SQL instance.
resource "google_vpc_access_connector" "connector" {
  project       = var.project_id
  name          = "${var.name}-connector"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.10.1.0/28"
  machine_type  = "e2-micro"
  min_instances = 2
  max_instances = 3

  depends_on = [google_service_networking_connection.private_vpc_connection]
}
