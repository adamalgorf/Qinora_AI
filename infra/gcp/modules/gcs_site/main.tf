resource "google_storage_bucket" "site" {
  project                     = var.project_id
  name                        = "${var.project_id}-${var.name}-frontend"
  location                    = var.location
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  labels                      = var.labels

  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html" # SPA fallback for client-side routing
  }

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }
}

# Public read so the load balancer's backend bucket can serve objects directly.
resource "google_storage_bucket_iam_member" "public_read" {
  bucket = google_storage_bucket.site.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Backend bucket for the external HTTPS load balancer, with Cloud CDN enabled.
# Cache-Control headers should be set at upload time by the deploy pipeline
# (e.g. `gcloud storage cp --cache-control` for hashed static assets vs.
# short/no-cache for index.html) since Terraform doesn't manage object content.
resource "google_compute_backend_bucket" "site" {
  project     = var.project_id
  name        = "${var.name}-frontend-backend"
  bucket_name = google_storage_bucket.site.name
  enable_cdn  = true

  cdn_policy {
    cache_mode        = "CACHE_ALL_STATIC"
    client_ttl        = 3600
    default_ttl       = 3600
    max_ttl           = 86400
    negative_caching  = true
    serve_while_stale = 86400
  }
}
