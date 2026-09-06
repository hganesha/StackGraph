terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "5.40.0"
    }
  }
}

resource "aws_db_instance" "ledger" {
  identifier     = "ledger"
  engine         = "postgres"
  engine_version = "16.2"
  instance_class = "db.t4g.medium"
}
