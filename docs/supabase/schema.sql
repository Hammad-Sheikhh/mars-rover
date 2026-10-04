-- Mars Rover: recommended Supabase schema + row-level security.
-- Derived from the payloads the firmware sends. Review against your live
-- project before running (Supabase dashboard -> SQL editor).
--
-- Principle: the anon key is effectively public (it ships in firmware),
-- so devices may only INSERT. Nothing anonymous can update or delete.

-- ---------- Tables ----------
create table if not exists public.sensor_readings (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  temperature real,
  humidity    real,
  ldr_state   text check (ldr_state in ('Day', 'Night')),
  pressure    real,
  altitude    real,
  pitch       real,
  roll        real,
  vibration   real,
  last_event  text check (char_length(last_event) <= 64)
);

create table if not exists public.camera_captures (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  image_url   text not null check (char_length(image_url) <= 512)
);

-- ---------- Row-level security ----------
alter table public.sensor_readings enable row level security;
alter table public.camera_captures enable row level security;

-- Devices (anon) may insert telemetry.
create policy "anon insert readings" on public.sensor_readings
  for insert to anon with check (true);
create policy "anon insert captures" on public.camera_captures
  for insert to anon with check (true);

-- Read access: keep it for signed-in users only. If a public read-only view
-- is needed later, add a separate SELECT policy for anon deliberately.
create policy "auth read readings" on public.sensor_readings
  for select to authenticated using (true);
create policy "auth read captures" on public.camera_captures
  for select to authenticated using (true);

-- ---------- Storage ----------
-- Bucket "rover_images" is public (images are readable by URL).
insert into storage.buckets (id, name, public)
values ('rover_images', 'rover_images', true)
on conflict (id) do nothing;

create policy "anon upload rover images" on storage.objects
  for insert to anon
  with check (bucket_id = 'rover_images');

-- cam1 currently sends "x-upsert: true", which also needs UPDATE permission.
-- Filenames are unique, so prefer removing that header and dropping this policy.
create policy "anon upsert rover images" on storage.objects
  for update to anon
  using (bucket_id = 'rover_images');
