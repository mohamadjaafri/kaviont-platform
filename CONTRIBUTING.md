# Contributing

Kaviont is an independent engineering reference project. Keep examples generic and do not add real credentials, customer data, employer code, or confidential architecture.

## Before opening a pull request

Run the container-first checks that apply to your change:

```bash
make fmt-check
make terraform-validate
make app-test
make helm-check
make image-build
make container-test
```

For rapid API development, use `make dev-up` and `make dev-down`. Use `make local-up` when you need to test the chart and Argo CD reconciliation on Kubernetes. The local cluster is disposable and does not require Azure.

## Change expectations

- Keep Terraform modules small and single-purpose.
- Prefer managed identities over credentials stored in configuration.
- Add variable validation for unsafe or ambiguous inputs.
- Keep Helm workloads non-root and resource-bounded by default.
- Document security, availability, cost, and operational trade-offs.
- Update the architecture decision records and runbooks when design behavior changes.
