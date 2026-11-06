-- 0041 Stage reasons.
-- Invalid gets "booking_rejected": a new lead whose only booking request staff rejected moves to Invalid with
-- this reason (POST /crm/requests/{id}/reject). Lost accepts "not_reachable", which the CRM has always offered
-- ("Not reachable") but the database refused; "no_response" stays valid for older rows.

alter table app.leads drop constraint leads_stage_reason;
alter table app.leads add constraint leads_stage_reason check (
  (stage = 'lost' and stage_reason is not null
     and stage_reason in ('not_reachable', 'no_response', 'not_interested', 'price', 'chose_another_clinic', 'other'))
  or (stage = 'invalid' and stage_reason is not null
     and stage_reason in ('wrong_number', 'spam', 'duplicate', 'test', 'booking_rejected'))
  or (stage not in ('lost', 'invalid') and stage_reason is null)
);
