# App Runner needs an IAM role to pull from ECR (the "access role" below) -
# the separate instance role the running container assumes to read its
# Secrets Manager secrets lives in secrets.tf, alongside the secrets
# themselves.

data "aws_iam_policy_document" "apprunner_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["build.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apprunner_ecr_access" {
  name               = "${var.project_name}-apprunner-ecr-access"
  assume_role_policy = data.aws_iam_policy_document.apprunner_assume.json
}

resource "aws_iam_role_policy_attachment" "apprunner_ecr_access" {
  role       = aws_iam_role.apprunner_ecr_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

resource "aws_apprunner_service" "backend" {
  service_name = "${var.project_name}-backend"

  source_configuration {
    image_repository {
      image_identifier      = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
      image_repository_type = "ECR"

      image_configuration {
        port = "8000"

        runtime_environment_variables = {
          QINORA_PERSISTENCE       = "postgres"
          QINORA_POSTGRES_TENANT_ID = var.postgres_tenant_id
          LLM_PROVIDER             = "openai"
          OPENAI_MODEL              = var.openai_model
          CORS_ALLOWED_ORIGINS      = "https://${aws_apprunner_service.frontend.service_url}"
        }

        runtime_environment_secrets = {
          DATABASE_URL             = aws_secretsmanager_secret.database_url.arn
          OPENAI_API_KEY           = aws_secretsmanager_secret.openai_api_key.arn
          EMAIL_WEBHOOK_SECRET     = aws_secretsmanager_secret.email_webhook_secret.arn
          QINORA_AUTH_TOKEN_SECRET = aws_secretsmanager_secret.auth_token_secret.arn
        }
      }
    }

    auto_deployments_enabled = false

    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr_access.arn
    }
  }

  instance_configuration {
    cpu             = "1024"
    memory          = "2048"
    instance_role_arn = aws_iam_role.apprunner_instance.arn
  }

  network_configuration {
    egress_configuration {
      egress_type       = "VPC"
      vpc_connector_arn = aws_apprunner_vpc_connector.backend.arn
    }
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/ready"
    healthy_threshold   = 1
    unhealthy_threshold = 5
    interval            = 10
    timeout             = 5
  }

  tags = { Name = "${var.project_name}-backend" }
}

resource "aws_apprunner_service" "frontend" {
  service_name = "${var.project_name}-frontend"

  source_configuration {
    image_repository {
      image_identifier      = "${aws_ecr_repository.frontend.repository_url}:${var.frontend_image_tag}"
      image_repository_type = "ECR"

      image_configuration {
        port = "80"
      }
    }

    auto_deployments_enabled = false

    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr_access.arn
    }
  }

  instance_configuration {
    cpu    = "256"
    memory = "512"
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/health"
    healthy_threshold   = 1
    unhealthy_threshold = 5
    interval            = 10
    timeout             = 5
  }

  tags = { Name = "${var.project_name}-frontend" }
}

output "backend_url" {
  value = "https://${aws_apprunner_service.backend.service_url}"
}

output "frontend_url" {
  value = "https://${aws_apprunner_service.frontend.service_url}"
}
