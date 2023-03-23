terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}

resource "aws_codecommit_repository" "realms_repo" {
  repository_name = "realms"
  description     = "A repository holding all realms data"

  provisioner "local-exec" {
    command = "chmod +x scripts/push_realm_data.sh && scripts/push_realm_data.sh ${aws_codecommit_repository.realms_repo.repository_name}"
  }
}

module "dynamodb_table" {
  source = "terraform-aws-modules/dynamodb-table/aws"

  name      = "realms_state"
  hash_key  = "connection_id"

  attributes = [
    {
      name = "connection_id"
      type = "S"
    }
  ]
}

