resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds"
  description = "Postgres access from the backend App Runner connector and ECS workers only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-rds-sg" }
}

resource "aws_db_instance" "main" {
  identifier     = "${var.project_name}-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.t4g.micro"

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "qinora"
  username = "qinora_admin"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  # 0 (no automated backups) because this account is currently on AWS's
  # restricted free plan, which rejects any backup retention period - raise
  # this once the account plan is upgraded.
  backup_retention_period = 0
  deletion_protection     = true
  skip_final_snapshot     = false
  final_snapshot_identifier = "${var.project_name}-db-final"

  tags = { Name = "${var.project_name}-db" }
}

# App code appends ?sslmode=require itself (see docs/aws-migration-runbook.md) -
# psycopg passes the DSN straight through, no code change needed for RDS.
output "database_url_no_credentials" {
  value = "postgres://<user>:<password>@${aws_db_instance.main.address}:5432/${aws_db_instance.main.db_name}?sslmode=require"
}
