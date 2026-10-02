# Plan: Add Redis caching to the API

This plan adds a Redis caching layer in front of the slow reporting endpoints.
Estimated effort: 2 days.

## Overview

We will introduce caching to reduce database load on the reporting endpoints.
No API contract changes. Rollback is a config flag.

## Step 1: Add the Redis client

Install the `redis` package and create a shared client module at
`app/cache.py`. Connection settings come from environment variables.
The client will be consumed by the decorator built in PLAN_004.

## Step 2: Cache decorator

Build a `@cached(ttl=...)` decorator in `app/cache.py` that wraps
reporting endpoints. Depends on the client from PLAN_002.

## Step 3: Wire up endpoints

Apply the decorator to `/reports/*` routes. Invalidate on writes.

## Acceptance Criteria

- All existing tests pass.
- p95 latency on `/reports/summary` under 200ms with a warm cache.
- Cache can be disabled via `CACHE_ENABLED=false`.
