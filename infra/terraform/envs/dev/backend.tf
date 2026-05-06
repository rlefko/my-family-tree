# Remote state configured after running the bootstrap module. The state bucket
# and lock table names come from `bootstrap`'s outputs.
#
# Uncomment and edit before running `terraform init`:
#
# terraform {
#   backend "s3" {
#     bucket         = "my-family-tree-tfstate-<account>-<region>"
#     key            = "envs/dev/terraform.tfstate"
#     region         = "us-east-1"
#     dynamodb_table = "my-family-tree-tflock"
#     encrypt        = true
#   }
# }
