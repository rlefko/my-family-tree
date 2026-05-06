# Remote state. Uncomment after running bootstrap.
#
# terraform {
#   backend "s3" {
#     bucket         = "my-family-tree-tfstate-<account>-<region>"
#     key            = "envs/prod/terraform.tfstate"
#     region         = "us-east-1"
#     dynamodb_table = "my-family-tree-tflock"
#     encrypt        = true
#   }
# }
