"""Phase 1 ownership foundation and RLS."""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    create type public.merchant_role as enum ('OWNER','ADMIN','ANALYST');
    create table public.profiles (id uuid primary key references auth.users(id) on delete cascade, display_name varchar(120), created_at timestamptz not null default now(), updated_at timestamptz not null default now());
    create table public.merchants (id uuid primary key default gen_random_uuid(), name varchar(160) not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
    create table public.merchant_users (merchant_id uuid references public.merchants(id) on delete cascade, user_id uuid references public.profiles(id) on delete cascade, role public.merchant_role not null, created_at timestamptz not null default now(), primary key(merchant_id,user_id));
    create table public.agent_sessions (id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade, merchant_id uuid references public.merchants(id) on delete set null, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
    create table public.intents (id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade, merchant_id uuid references public.merchants(id) on delete set null, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
    create table public.mandates (id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
    create table public.audit_events (id uuid primary key default gen_random_uuid(), user_id uuid references public.profiles(id) on delete set null, merchant_id uuid references public.merchants(id) on delete set null, event_type varchar(100) not null, created_at timestamptz not null default now());
    create index agent_sessions_user_idx on public.agent_sessions(user_id); create index intents_user_idx on public.intents(user_id); create index mandates_user_idx on public.mandates(user_id); create index audit_events_user_idx on public.audit_events(user_id); create index audit_events_merchant_idx on public.audit_events(merchant_id);
    create or replace function public.set_updated_at() returns trigger language plpgsql as $$ begin new.updated_at=now(); return new; end; $$;
    create trigger profiles_updated before update on public.profiles for each row execute function public.set_updated_at(); create trigger merchants_updated before update on public.merchants for each row execute function public.set_updated_at(); create trigger agent_sessions_updated before update on public.agent_sessions for each row execute function public.set_updated_at(); create trigger intents_updated before update on public.intents for each row execute function public.set_updated_at(); create trigger mandates_updated before update on public.mandates for each row execute function public.set_updated_at();
    create or replace function public.handle_new_auth_user() returns trigger language plpgsql security definer set search_path=public as $$ begin insert into public.profiles(id,display_name) values(new.id,coalesce(new.raw_user_meta_data->>'display_name',split_part(new.email,'@',1))) on conflict do nothing; return new; end; $$; create trigger auth_user_profile after insert on auth.users for each row execute function public.handle_new_auth_user();
    alter table public.profiles enable row level security; alter table public.merchants enable row level security; alter table public.merchant_users enable row level security; alter table public.agent_sessions enable row level security; alter table public.intents enable row level security; alter table public.mandates enable row level security; alter table public.audit_events enable row level security;
    create policy profiles_own on public.profiles for all to authenticated using (id=auth.uid()) with check (id=auth.uid()); create policy merchant_users_own on public.merchant_users for select to authenticated using (user_id=auth.uid()); create policy merchants_member on public.merchants for select to authenticated using (exists(select 1 from public.merchant_users mu where mu.merchant_id=merchants.id and mu.user_id=auth.uid())); create policy sessions_own on public.agent_sessions for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid()); create policy intents_own on public.intents for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid()); create policy mandates_own on public.mandates for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid()); create policy audit_read on public.audit_events for select to authenticated using(user_id=auth.uid() or exists(select 1 from public.merchant_users mu where mu.merchant_id=audit_events.merchant_id and mu.user_id=auth.uid()));
    """)


def downgrade():
    op.execute(
        "drop trigger if exists auth_user_profile on auth.users; drop table if exists public.audit_events,public.mandates,public.intents,public.agent_sessions,public.merchant_users,public.merchants,public.profiles cascade; drop function if exists public.handle_new_auth_user cascade; drop function if exists public.set_updated_at cascade; drop type if exists public.merchant_role;"
    )
