# Contributing

Kaviont is an independent engineering reference project. Keep examples generic and do not add real credentials, customer data, employer code, or confidential architecture.

## Before opening a pull request

Run the checks that apply to your change:

```bash
make fmt-check
make terraform-validate
make app-test
make helm-check
make image-build
```

## Change expectations

- Keep Terraform modules small and single-purpose.
- Prefer managed identities over credentials stored in configuration.
- Add variable validation for unsafe or ambiguous inputs.
- Keep Helm workloads non-root and resource-bounded by default.
- Document security, availability, cost, and operational trade-offs.
- Update the architecture decision records and runbooks when design behavior changes.
