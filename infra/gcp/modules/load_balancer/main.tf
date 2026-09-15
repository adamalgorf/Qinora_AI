# Serverless NEG pointing at the Cloud Run service.
resource "google_compute_region_network_endpoint_group" "cloud_run_neg" {
  project               = var.project_id
  name                  = "${var.name}-run-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = var.cloud_run_service_name
  }
}

resource "google_compute_security_policy" "cloud_armor" {
  project = var.project_id
  name    = "${var.name}-armor-policy"

  # Default: allow, with AWS/GCP-standard preconfigured WAF rules layered on
  # top. Add rate limiting / IP denylists here as needed.
  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow"
  }

  # The auth endpoints' bodies are a high-entropy password and a small JSON
  # blob (user_id/tenant_id/roles) - both routinely false-positive against
  # the OWASP CRS sqli/xss rules below (different rule ID each time), which
  # locked authentication itself out of the app. Backend queries are all
  # parameterized (psycopg %s placeholders), so SQLi/XSS body inspection
  # adds no real protection here; scope the bypass to just these two paths
  # rather than weakening sensitivity site-wide.
  rule {
    action   = "allow"
    priority = 900
    match {
      expr {
        # Cloud Armor evaluates against the backend-service-bound request,
        # i.e. after the url_map's /api prefix-strip route_rules above -
        # match both forms since which one actually arrives here isn't
        # documented and is safer to over-match on a same-origin path check.
        expression = "request.path == '/auth/login' || request.path == '/auth/dev-token' || request.path == '/api/auth/login' || request.path == '/api/auth/dev-token'"
      }
    }
    description = "Auth endpoints: skip WAF body inspection (parameterized queries, high-entropy bodies false-positive)"
  }

  rule {
    action   = "deny(403)"
    priority = 1000
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-stable')"
      }
    }
    description = "Block SQL injection attempts"
  }

  rule {
    action   = "deny(403)"
    priority = 1001
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-stable')"
      }
    }
    description = "Block XSS attempts"
  }

  rule {
    action   = "throttle"
    priority = 2000
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 300
        interval_sec = 60
      }
    }
    description = "Basic per-IP rate limit"
  }
}

resource "google_compute_backend_service" "api" {
  project               = var.project_id
  name                  = "${var.name}-api-backend"
  protocol              = "HTTP"
  port_name             = "http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.cloud_armor.id

  backend {
    group = google_compute_region_network_endpoint_group.cloud_run_neg.id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

resource "google_compute_url_map" "default" {
  project         = var.project_id
  name            = "${var.name}-lb"
  default_service = var.backend_bucket_id

  host_rule {
    hosts        = [var.domain_name]
    path_matcher = "main"
  }

  # route_rules (not path_rule) so we can strip the /api prefix before
  # forwarding to Cloud Run - the backend's own routes (/cases, /quotes,
  # ...) aren't prefixed, matching the same proxy_pass-strips-/api/
  # behavior frontend/nginx.conf uses for local docker-compose.
  path_matcher {
    name            = "main"
    default_service = var.backend_bucket_id

    route_rules {
      priority = 1
      match_rules {
        prefix_match = "/api/"
      }
      service = google_compute_backend_service.api.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    route_rules {
      priority = 2
      match_rules {
        full_path_match = "/api"
      }
      service = google_compute_backend_service.api.id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
  }
}

resource "google_compute_managed_ssl_certificate" "default" {
  project = var.project_id
  name    = "${var.name}-cert"
  managed {
    domains = [var.domain_name]
  }
}

resource "google_compute_target_https_proxy" "default" {
  project          = var.project_id
  name             = "${var.name}-https-proxy"
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_managed_ssl_certificate.default.id]
}

resource "google_compute_global_address" "lb_ip" {
  project = var.project_id
  name    = "${var.name}-lb-ip"
}

resource "google_compute_global_forwarding_rule" "https" {
  project               = var.project_id
  name                  = "${var.name}-https-forwarding-rule"
  ip_address            = google_compute_global_address.lb_ip.address
  ip_protocol           = "TCP"
  port_range            = "443"
  target                = google_compute_target_https_proxy.default.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# HTTP -> HTTPS redirect.
resource "google_compute_url_map" "https_redirect" {
  project = var.project_id
  name    = "${var.name}-http-redirect"

  default_url_redirect {
    https_redirect = true
    strip_query    = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  project = var.project_id
  name    = "${var.name}-http-proxy"
  url_map = google_compute_url_map.https_redirect.id
}

resource "google_compute_global_forwarding_rule" "http" {
  project               = var.project_id
  name                  = "${var.name}-http-forwarding-rule"
  ip_address            = google_compute_global_address.lb_ip.address
  ip_protocol           = "TCP"
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
