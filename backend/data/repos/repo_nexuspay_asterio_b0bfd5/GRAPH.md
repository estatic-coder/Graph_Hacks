# NexusPay graph

```mermaid
flowchart TD
  create_payment --> submit
  submit --> decide
  submit --> place_hold
  submit --> save
  submit --> record
  submit --> send_notice
  submit --> process
  approve_payment --> approve
  approve --> load
  approve --> place_hold
  approve --> record
  approve --> process
  reject_payment --> reject
  reject --> load
  reject --> record
  process --> authorize
  process --> capture_hold
  process --> release_hold
  process --> record
  process --> send_notice
  process --> save
  refund_payment --> refund
  refund --> load
  refund --> record
  refund --> send_notice
  refund --> save
  get_payment --> load
  cleanup_orphan_holds --> release_hold
  cleanup_orphan_holds --> record
  submit -. "review saved; later external approval" .-> approve
  submit -. "review saved; later external rejection" .-> reject
```

Solid arrows: static direct calls. Dashed arrows: state-mediated workflow, **not** CALLS edges.

Important: `process()` is reached only after successful hold placement. Review decisions return early. Blocked payments return without saving. Refunds are separate entry points and do not reverse the original ledger debit in this synthetic system.
