create table invoice (
  id uuid primary key,
  customer_id uuid not null,
  amount_minor bigint not null,
  issued_at timestamptz not null
);
