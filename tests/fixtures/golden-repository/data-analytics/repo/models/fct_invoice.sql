select
  invoice_id,
  customer_id,
  amount_minor,
  issued_at
from {{ ref('stg_invoice') }}
