# Architecture and design decisions

## Request path and isolation

```text
JWT -> DRF authentication -> UserProfile(org, role, properties)
    -> scoped_projects() -> serializer/view
    -> persisted AnalyticsRollup (worker refresh) -> React
Approval transaction -> ApprovalEvent -> tenant-{org_id} Channels group
```

Every project endpoint obtains its queryset from `scoped_projects`; it filters organization
first and, for non-admins, filters the entitlement M2M. Detail lookup therefore returns 404
for an ID outside the caller's scope, preventing ID enumeration while preserving one central
enforcement point. Analytics derives the same property scope before selecting a rollup or
calculating a cache miss. A future export endpoint must accept this same scoped queryset,
never a raw `Project.objects` queryset.

The platform also has a separate `super_admin` role for company leadership. This account has
no organization assignment, can inspect global analytics and all tenant projects, and can
manage organizations. It is intentionally distinct from `org_admin`, which remains limited
to one customer organization.

## Analytics

Celery computes organization and property rollups into `AnalyticsRollup`; Redis is the
broker and Channels layer. In production, writes enqueue a refresh task (coalesced by org)
and a periodic reconciliation recomputes all rollups. The dashboard trades a bounded
staleness window for predictable reads: a rollup read is constant-time and has no large
GROUP BY. The demo computes a cache miss so first use is correct; steady-state reads use
the stored payload. Incremental event-driven rollups are a later optimization.

## Workflow and concurrency

Approval uses a database transaction and `select_for_update()`. The transition is checked
against the current status and an optional version supplied by the client. The row lock
serializes two approvers; the second request sees a changed status/version and receives a
conflict. The event is written in the same transaction as the state change. In production,
an outbox row would make websocket publication retryable without duplicating state changes.

## Real-time

Connections authenticate before joining `tenant-{organization_id}`. Approval events are sent
only to that group, so a socket cannot subscribe to another organization by changing a URL.
At 10k sockets, use Redis pub/sub behind multiple ASGI instances, keep payloads small, and
coalesce refresh requests in the client. A tenant/property-specific channel can be added for
large organizations.

## Production DB and deployment

The slice runs SQLite in tests and Postgres in Compose. Azure SQL requires the Django
Microsoft backend, `mssql-django`, ODBC Driver 18, UTC connection settings, and migration
validation against the production engine. Keep composite indexes on `(organization_id,
property_id,status)` and `(organization_id,fiscal_period,category)`, use a bounded connection
pool, and place rollup reads on a read replica only if freshness requirements allow it.
AKS separates API/ASGI, Celery workers, and frontend deployments; Redis and the database are
managed services with network policies and secret-backed credentials.

## Tradeoffs

1. **Persisted rollups over live queries:** predictable latency and scalable reads, in
   exchange for bounded staleness and a reconciliation job.
2. **404 for unauthorized IDs:** it prevents cross-tenant existence leaks, at the cost of
   less diagnostic detail for a caller.
3. **JWT + websocket group auth:** stateless API scaling and simple dashboard updates, in
   exchange for token revocation complexity; production should add short access-token TTLs,
   refresh rotation, and an outbox for reliable events.
