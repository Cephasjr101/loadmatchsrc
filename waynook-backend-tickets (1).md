# Backend Tickets — List a Track

## B1. Database schema + migrations
- Create tables: `tracks`, `track_photos`, `track_availability`
- Add to `users`: `phone`, `phone_verified`, `trusted_host` (bool, default false)
- Indexes: `tracks(status)`, `tracks(host_id)`, `tracks(country, region, city)` for browse/search
- Enums: track type, surface, direction, price unit, contact mode, listing status
- Acceptance: migrations run clean on empty + existing prod-like DB

## B2. Auth gates
- Middleware: require verified email to create/update listings
- Middleware: require verified phone to submit (not for drafts)
- Acceptance: unverified users get 403 with a clear error code; drafts allowed

## B3. Track CRUD endpoints
- `POST /api/tracks` — create as DRAFT
- `PATCH /api/tracks/:id` — update (owner only; enforce review-requeue rules)
- `GET /api/tracks/:id` — owner view (full) vs public view (redacted: address_hidden respected, draft state returns 404)
- `DELETE /api/tracks/:id` — soft delete
- Enforce: edits to name/location/price on ACTIVE listings set status → PENDING_REVIEW; other fields update live
- Acceptance: ownership enforced on every route; can't edit others' tracks

## B4. Submit + moderation state machine
- `POST /api/tracks/:id/submit` — DRAFT/PENDING_REVIEW → PENDING_REVIEW (sets submitted_at)
- `POST /api/admin/tracks/:id/approve` → ACTIVE, sets reviewed_at/reviewed_by; grants `trusted_host` if host's first approval
- `POST /api/admin/tracks/:id/reject` → REJECTED with reason (returned to host)
- `POST /api/admin/tracks/:id/flag` / unflag — UNDER_REVIEW ↔ ACTIVE
- Admin-only middleware (role check)
- Acceptance: invalid transitions rejected (e.g. can't approve a DRAFT); full audit trail in DB

## B5. Auto-publish for trusted hosts
- On submit: if `trusted_host` and passes spam gates → ACTIVE immediately; else PENDING_REVIEW
- Acceptance: unit tests for both paths

## B6. Spam & abuse gates
- Rate limit: 3 submissions/day unverified, 10/day trusted (per account)
- Submit-time checks: max links in description (2), banned keyword list, duplicate name+city warning
- Image: perceptual hash check vs existing listings on photo upload
- Acceptance: each gate unit-tested; limits return 429 with retry info

## B7. Image upload pipeline
- `POST /api/tracks/:id/photos` — presigned upload URLs (S3/compatible); enforce type (JPG/PNG/WebP), size ≤10MB
- Async job: compress/resize (cover 1600px, thumbs 400px), run moderation scan, hash for dedupe
- `DELETE /api/photos/:id`, `PATCH /api/tracks/:id/photos/order` + set cover
- Acceptance: garbage files rejected; orphan cleanup job for unlinked uploads >24h

## B8. Geocoding
- Geocode address on save; store lat/lng
- Fallback: accept manual pin when geocode fails → flag `address_needs_review` for admin
- Never expose exact coords in public API when `address_hidden` is true — return centroid of city/area instead
- Acceptance: redaction covered by API tests

## B9. Availability engine
- CRUD for weekly patterns + closed-date exceptions
- Store in `track_availability`; no booking conflict logic yet (Phase 2)
- Acceptance: overlapping/invalid ranges rejected

## B10. Expiry job
- Daily cron: listings with `last_host_activity_at` > 12 months → email host "verify still active" → UNPUBLISHED after 14 days no response
- Host activity = login or any listing edit; update `last_host_activity_at` on those events
- Acceptance: dry-run mode logs what it would unpublish

## B11. Notifications
- Emails: submitted-received, approved, rejected(+reason), flagged, expiring soon, unpublished
- Phase 1: email only; in-app inbox later
- Acceptance: templates render, all events fire, no send on draft autosave

## B12. Public browse API
- `GET /api/tracks` — filter by type/location, paginated, ACTIVE only, redacted location
- `GET /api/tracks/:id` public view — cover photo, gallery, facilities, availability summary, contact mode
- Acceptance: drafts/pending never leak; pagination capped

---

### Dependency order
B1 → B2 → B3 → B7 → B8 → B9 → B4 → B5 → B6 → B11 → B10 → B12
(B12 can start once B3 lands; B10 is independent)

### Phase 1 cut
Skip or stub: B9 (accept simple JSONB hours field), B10 (manual unpublish only), B11 (approve/reject emails only)
