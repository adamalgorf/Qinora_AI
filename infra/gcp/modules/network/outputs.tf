output "network_id" {
  value = google_compute_network.vpc.id
}

output "network_self_link" {
  value = google_compute_network.vpc.self_link
}

output "subnet_id" {
  value = google_compute_subnetwork.subnet.id
}

output "vpc_connector_id" {
  value = google_vpc_access_connector.connector.id
}

output "private_vpc_connection" {
  value = google_service_networking_connection.private_vpc_connection.id
}
