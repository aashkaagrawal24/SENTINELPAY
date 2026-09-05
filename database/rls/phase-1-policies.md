# Phase 1 RLS

Migration `0001_foundation` enables RLS for every exposed ownership table. Profiles, sessions, intents, and mandates are scoped to `auth.uid()`. Merchant records are visible only through a matching membership. Audit records are readable by the related user or merchant member. Service-role access is backend-only.
