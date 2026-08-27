# App Runner's `runtime_environment_secrets` block only accepts Secrets
# Manager (or SSM Parameter Store) ARNs, not plaintext - so every secret the
# backend needs is stored here and referenced by ARN in apprunner.tf.

resource "aws_secretsmanager_secret" "database_url" {
  name = "${var.project_name}/database_url"
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = "postgres://qinora_admin:${var.db_password}@${aws_db_instance.main.address}:5432/${aws_db_instance.main.db_name}?sslmode=require"
}

resource "aws_secretsmanager_secret" "openai_api_key" {
  name = "${var.project_name}/openai_api_key"
}

resource "aws_secretsmanager_secret_version" "openai_api_key" {
  secret_id     = aws_secretsmanager_secret.openai_api_key.id
  secret_string = var.openai_api_key
}

resource "aws_secretsmanager_secret" "email_webhook_secret" {
  name = "${var.project_name}/email_webhook_secret"
}

resource "aws_secretsmanager_secret_version" "email_webhook_secret" {
  secret_id     = aws_secretsmanager_secret.email_webhook_secret.id
  secret_string = var.email_webhook_secret
}

resource "aws_secretsmanager_secret" "auth_token_secret" {
  name = "${var.project_name}/auth_token_secret"
}

resource "aws_secretsmanager_secret_version" "auth_token_secret" {
  secret_id     = aws_secretsmanager_secret.auth_token_secret.id
  secret_string = var.auth_token_secret
}

# Instance role: what the *running* backend container/task can access -
# read-only access to just these four secrets, for App Runner and the ECS
# worker tasks alike.
data "aws_iam_policy_document" "read_qinora_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.database_url.arn,
      aws_secretsmanager_secret.openai_api_key.arn,
      aws_secretsmanager_secret.email_webhook_secret.arn,
      aws_secretsmanager_secret.auth_token_secret.arn,
    ]
  }
}

resource "aws_iam_policy" "read_qinora_secrets" {
  name   = "${var.project_name}-read-secrets"
  policy = data.aws_iam_policy_document.read_qinora_secrets.json
}

data "aws_iam_policy_document" "apprunner_instance_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["tasks.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apprunner_instance" {
  name               = "${var.project_name}-apprunner-instance"
  assume_role_policy = data.aws_iam_policy_document.apprunner_instance_assume.json
}

resource "aws_iam_role_policy_attachment" "apprunner_instance_secrets" {
  role       = aws_iam_role.apprunner_instance.name
  policy_arn = aws_iam_policy.read_qinora_secrets.arn
}
