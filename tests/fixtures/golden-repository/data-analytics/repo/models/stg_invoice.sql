select id as invoice_id, customer_id, amount_minor, issued_at from {{ source('billing', 'invoice') }}
