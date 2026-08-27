# The three worker scripts (backend/src/qinora/workers/*.py) are one-shot
# batch jobs - docker-compose.yml fakes them into long-running loops for
# local dev, but the code's own comments say they're meant to be invoked by
# an external scheduler. On AWS that's Fargate tasks on EventBridge
# Scheduler rate rules, reusing the same backend image (just a different
# `command`), not a long-running service.

resource "aws_ecs_cluster" "workers" {
  name = "${var.project_name}-workers"
}

resource "aws_cloudwatch_log_group" "workers" {
  name              = "/ecs/${var.project_name}-workers"
  retention_in_days = 14
}

data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker_execution" {
  name               = "${var.project_name}-worker-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
}

resource "aws_iam_role_policy_attachment" "worker_execution_managed" {
  role       = aws_iam_role.worker_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# The execution role also needs to read the Secrets Manager ARNs it injects
# as container env vars at task startup (distinct from the task role below,
# which is what the running application code can access).
resource "aws_iam_role_policy_attachment" "worker_execution_secrets" {
  role       = aws_iam_role.worker_execution.name
  policy_arn = aws_iam_policy.read_qinora_secrets.arn
}

resource "aws_iam_role" "worker_task" {
  name               = "${var.project_name}-worker-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
}

resource "aws_iam_role_policy_attachment" "worker_task_secrets" {
  role       = aws_iam_role.worker_task.name
  policy_arn = aws_iam_policy.read_qinora_secrets.arn
}

locals {
  worker_env = [
    { name = "QINORA_PERSISTENCE", value = "postgres" },
    { name = "QINORA_POSTGRES_TENANT_ID", value = var.postgres_tenant_id },
    { name = "LLM_PROVIDER", value = "openai" },
    { name = "OPENAI_MODEL", value = var.openai_model },
  ]

  worker_secrets = [
    { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
    { name = "OPENAI_API_KEY", valueFrom = aws_secretsmanager_secret.openai_api_key.arn },
    { name = "EMAIL_WEBHOOK_SECRET", valueFrom = aws_secretsmanager_secret.email_webhook_secret.arn },
    { name = "QINORA_AUTH_TOKEN_SECRET", valueFrom = aws_secretsmanager_secret.auth_token_secret.arn },
  ]

  workers = {
    outbound_mailer = {
      module      = "qinora.workers.outbound_mailer"
      schedule    = "rate(1 minute)"  # was a 30s loop in docker-compose.yml
    }
    tracking_simulator = {
      module      = "qinora.workers.tracking_simulator"
      schedule    = "rate(1 minute)"  # was a 60s loop
    }
    stale_request_escalator = {
      module      = "qinora.workers.stale_request_escalator"
      schedule    = "rate(5 minutes)" # matches the 300s loop exactly
    }
  }
}

resource "aws_ecs_task_definition" "worker" {
  for_each = local.workers

  family                   = "${var.project_name}-${replace(each.key, "_", "-")}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                       = "256"
  memory                    = "512"
  execution_role_arn        = aws_iam_role.worker_execution.arn
  task_role_arn             = aws_iam_role.worker_task.arn

  container_definitions = jsonencode([{
    name      = each.key
    image     = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
    essential = true
    command   = ["python", "-m", each.value.module]
    environment = local.worker_env
    secrets     = local.worker_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.workers.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = each.key
      }
    }
  }])
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.project_name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler_run_task" {
  statement {
    actions   = ["ecs:RunTask"]
    resources = [for t in aws_ecs_task_definition.worker : t.arn]
  }

  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.worker_execution.arn, aws_iam_role.worker_task.arn]
  }
}

resource "aws_iam_role_policy" "scheduler_run_task" {
  name   = "${var.project_name}-scheduler-run-task"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_run_task.json
}

resource "aws_scheduler_schedule" "worker" {
  for_each = local.workers

  name                         = "${var.project_name}-${replace(each.key, "_", "-")}"
  schedule_expression          = each.value.schedule
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.workers.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.worker[each.key].arn
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = aws_subnet.private[*].id
        security_groups  = [aws_security_group.app.id]
        assign_public_ip = false
      }
    }
  }
}
