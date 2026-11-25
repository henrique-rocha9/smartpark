create table leituras (
  id bigint generated always as identity primary key,
  dispositivo text not null,
  grandeza text not null,
  vaga int not null,
  status text not null,
  valor numeric,
  unidade text default 'cm',
  criado_em timestamptz default now()
);

alter table leituras enable row level security;

grant all on table public.leituras to service_role;
grant usage, select on all sequences in schema public to service_role;
