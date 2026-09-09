output "lb_ip_address" {
  value = google_compute_global_address.lb_ip.address
}

output "ssl_certificate_id" {
  value = google_compute_managed_ssl_certificate.default.id
}
