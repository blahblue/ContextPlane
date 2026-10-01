# Sample coding task

Repository: `checkout-api`  
Environment: `production`

Implement a new endpoint that returns the current checkout-session status.

Before editing code:

1. Call `get_engineering_context` with:
   - `repository="checkout-api"`
   - `environment="production"`
   - `task="implement checkout session status endpoint"`
2. Call `get_policy_context` with the same repository/environment/task selectors.
3. Treat the returned engineering standards and security controls as the authoritative ContextPlane result for this task.
4. Do not treat the repository string itself as proof of authorization to any external system.
5. Make the smallest code change consistent with the returned context and add/update tests.

Expected demo behavior:

- `checkout-api` receives the shared pytest rule and FastAPI/SQLAlchemy checkout conventions.
- `catalog-api` receives the shared pytest rule and Django catalog conventions instead.
- checkout security context includes the mandatory secret-handling control.
- changing the authoritative seed and reloading it changes subsequent ContextPlane results without editing this task prompt.
