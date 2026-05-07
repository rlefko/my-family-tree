# Terraform bootstrap

One-time module that creates the remote-state S3 bucket and DynamoDB lock
table. Run with local state, then commit and switch the per-env stacks to
the remote backend (`envs/dev/backend.tf`, `envs/prod/backend.tf`).

```bash
cd infra/terraform/bootstrap
terraform init
terraform apply
# note the `state_bucket` and `lock_table` outputs and plug them into
# envs/dev/backend.tf and envs/prod/backend.tf.
```
