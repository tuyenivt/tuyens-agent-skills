---
name: rails-active-storage-patterns
description: "Active Storage Rails 7.2 - direct S3/GCS upload, content_type/size + magic-byte validation, libvips variants, purge_later, CarrierWave migration."
metadata:
  category: backend
  tags: [ruby, rails, active-storage, s3, upload, attachments]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the storage service (S3/GCS/Azure/disk) and image processor (libvips/ImageMagick).

## When to Use

- Adding file or image uploads to a model
- Configuring direct upload to avoid proxying through Puma
- Designing variant/preview pipelines
- Purging attachments on parent destroy or scheduling orphan cleanup
- Migrating from CarrierWave / Paperclip / Shrine
- Reviewing upload security (content-type, size, signed URL exposure)

## Rules

- Direct upload (`direct_upload: true`) for files > 1 MB - proxying through Puma blocks a worker for the upload duration
- Leave `dependent:` at its default `:purge_later` (omitting the option is compliant). `:purge_later` and `false` are the only values Rails honours - `purge_dependent_blob_later` fires on `:purge_later` alone, so `dependent: :purge` (or any other value) silently purges nothing and orphans the blob. The sync `purge` *method* is for admin/rake scripts
- Validate `content_type` and `byte_size` in the model (or via `active_storage_validations`) - Active Storage does no validation itself. `attach` on a persisted record with no unsaved changes calls plain `record.save`, so validations *do* run - but it returns `nil` instead of raising, so a rejected attach looks like success and leaves the blob (already a row and an object, on the direct-upload path) orphaned. Check the return value or `record.errors`, and purge on rejection. The genuinely unvalidated case is the other branch: when the record has unsaved attribute changes, `attach` defers to the next save and validates nothing at attach time
- Re-detect content type via magic bytes for sensitive uploads. Rails already re-identifies on attach (`identify_without_saving` sniffs the first 4 KB with Marcel), so the stored `content_type` is not simply the client's - but Marcel falls back to the client-declared type when the magic bytes are unrecognized, and that fallback is the hole. Run the check in the attach-time background job using `blob.open { |f| Marcel::MimeType.for(f) }` - streaming, not `blob.download` (loads the whole file into memory). Gate visibility on the result: a quarantine flag in `blob.metadata` (per-file, so it works for `has_many_attached`) holds the file from viewers until the sniff passes; purge on confirmed mismatch
- libvips is already the processor under `load_defaults 7.0`+ (`variant_processor = :vips`) - an app that never sets it is compliant, not a GAP. Only flag an explicit `:mini_magick`, or a missing `libvips` / `image_processing` install
- Variants are lazy by default; warm them in a background job for high-traffic paths
- Signed URLs only (`rails_blob_url` / `url_for`); never expose raw blob keys. Note the two knobs differ: `ActiveStorage.urls_expire_in` defaults to `nil`, so `rails_blob_url` signed ids never expire until you set it, and it is app-wide; the 5-minute default belongs to `service_urls_expire_in` on the redirect target. For a per-viewer window use `blob.url(expires_in: 5.minutes)` at the call site
- One service per environment in `config/storage.yml`; reference by symbol in `config.active_storage.service`; never hardcode bucket names

## Patterns

### Direct Upload to S3/GCS

```yaml
# config/storage.yml
amazon:
  service: S3
  access_key_id: <%= Rails.application.credentials.dig(:aws, :access_key_id) %>
  secret_access_key: <%= Rails.application.credentials.dig(:aws, :secret_access_key) %>
  region: ap-northeast-1
  bucket: app-production-uploads
  http_open_timeout: 5
  http_read_timeout: 10
```

```erb
<%= form.file_field :avatar, direct_upload: true %>
```

The form POSTs metadata to `/rails/active_storage/direct_uploads`, receives a signed PUT URL, uploads directly to S3, then submits with the resulting `signed_id`. Puma sees only the small metadata roundtrip.

Bucket CORS for browser PUT:

```
AllowedOrigins: https://app.example.com
AllowedMethods: PUT, POST
AllowedHeaders: Content-Type, Content-MD5, Content-Disposition, x-amz-acl, Origin
```

### Validation

```ruby
class User < ApplicationRecord
  has_one_attached :avatar, dependent: :purge_later

  AVATAR_TYPES = %w[image/jpeg image/png image/webp].freeze
  AVATAR_MAX_BYTES = 5.megabytes

  validate :avatar_constraints

  private

  def avatar_constraints
    return unless avatar.attached?
    errors.add(:avatar, "must be JPEG, PNG, or WebP") unless AVATAR_TYPES.include?(avatar.content_type)
    errors.add(:avatar, "must be <= 5 MB")            if avatar.byte_size > AVATAR_MAX_BYTES
  end
end
```

Or via `active_storage_validations`:

```ruby
validates :avatar, content_type: AVATAR_TYPES, size: { less_than: 5.megabytes }
```

Sensitive uploads (e.g., executables, PDFs): re-detect type via the streaming magic-byte check (Rules) before any human approves or views the file. Serve user content from a separate domain or with `Content-Disposition: attachment`.

Blob routes carry **no authorization** - anyone holding a signed URL reads the file for as long as it stays valid, and `ActiveStorage.urls_expire_in` is `nil` by default, so that is forever until you set it. For sensitive attachments gate through your own controller (authorize, then redirect to a URL signed per call: `blob.url(expires_in: 5.minutes)`). This applies to a customer reading their own document exactly as it does to an internal reviewer - the gate is ownership, not staff-ness.

### Variants and Warming

```ruby
class User < ApplicationRecord
  has_one_attached :avatar do |attachable|
    attachable.variant :thumb,  resize_to_fill: [80, 80]
    attachable.variant :medium, resize_to_fill: [320, 320]
  end
end
```

```erb
<%# Lazy - first request processes inline %>
<%= image_tag user.avatar.variant(:thumb) %>

<%# Warmed - background job has processed it %>
<%= image_tag user.avatar.variant(:thumb).processed %>
```

Warm on attachment for hot paths:

```ruby
class ProcessUploadJob
  include Sidekiq::Job

  def perform(blob_signed_id, record_global_id)
    record = GlobalID::Locator.locate(record_global_id)
    blob   = ActiveStorage::Blob.find_signed!(blob_signed_id)
    record.avatar.attach(blob)
    record.avatar.variant(:thumb).processed
    record.avatar.variant(:medium).processed
  end
end
```

This job is the attach point: the controller passes the direct-upload `signed_id` to it instead of attaching inline, and sensitive uploads run the magic-byte sniff (Rules) here, before the variants. When the controller does attach inline, drop the attach lines and enqueue with the record gid only - the job then just warms.

Non-image previews (PDF first page, video frame): `attachment.preview(resize_to_limit: [320, 320])` requires the system dependency (`poppler`/`mupdf` for PDF, `ffmpeg` for video) and only works when `attachment.previewable?`; guard rendering with `previewable?` and warm previews in the same background job as variants.

### Purge Semantics

| Method                       | Behavior                                   | Use when                              |
| ---------------------------- | ------------------------------------------ | ------------------------------------- |
| `attachment.purge`           | Sync delete blob + variants                | Rake/admin scripts                    |
| `attachment.purge_later`     | Enqueue `ActiveStorage::PurgeJob`          | Default; non-blocking                 |
| `dependent: :purge_later`    | On parent destroy, enqueue purge jobs      | All model attachments (the default)   |
| `dependent: false`           | On parent destroy, **nothing is purged**   | Never - the blob is orphaned and needs the unattached sweep |

Replacing a `has_one_attached` file destroys the old attachment and purges its blob via `purge_later` automatically - no manual cleanup on re-attach.

Orphan cleanup - direct uploads abandoned before form submit accumulate as unattached blobs:

```ruby
ActiveStorage::Blob.unattached.where("created_at < ?", 1.day.ago).find_each(&:purge_later)
```

Business retention (purge N days after an event) is its own scheduled job, distinct from orphan cleanup:

```ruby
LoanApplication.decided.where(decided_at: ..90.days.ago)
               .find_each { |app| app.income_documents.each(&:purge_later) }
```

### Migrating from CarrierWave / Paperclip (or disk -> S3)

1. `bin/rails active_storage:install` + migrate.
2. Keep the old uploader; add `has_one_attached :new_<name>` on the model.
3. Backfill rake: for each record, attach from the old storage. When source and target are the same S3 account (CW on S3), skip download-reupload: S3 server-side copy into the Active Storage key, then create the `ActiveStorage::Blob` row from the object's metadata (`ActiveStorage::Blob.create!(key:, filename:, byte_size:, checksum:, content_type:, service_name:)`; the `checksum` is base64-MD5 - multipart ETags aren't MD5, so compute it once per object or copy single-part), then `attach` that blob to the record - an unattached blob row is an orphan the cleanup rake will purge. Disk or cross-provider sources stream (`File.open` / `blob.open`) into `attach` - no copy shortcut. At millions of records, run as a sharded resumable backfill (`rails-work-splitter-patterns`).
4. Warm variants inside the backfill job (before reads flip), not lazily after.
5. Dual-read during transition (one helper/presenter owns it): `record.new_<name>.attached? ? record.new_<name> : record.<name>`.
6. Switch writes to Active Storage; backfill stragglers.
7. Drop the old column and uploader once legacy read traffic is 0.

Keep old data until new attachments are verified - plan the rollback. High-traffic public images: the Rails redirect URL itself is stable (with `urls_expire_in` nil there is no `exp` in it), but the S3 URL it 302s to rotates every `service_urls_expire_in` - 5 minutes by default - so a CDN caching the redirect ends up serving an expired target. Use proxy mode (`rails_storage_proxy_path`, stable URL, bytes through the app) behind the CDN, or a public-bucket service, before flipping reads.

Already on Active Storage and only changing services (disk -> S3, bucket move)? Skip the steps above: configure `ActiveStorage::Service::MirrorService` (primary + mirror in `storage.yml`), let writes hit both, then backfill and flip. Two traps in that backfill:

- `blob.mirror_later` no-ops on exactly the blobs you are targeting. It is guarded by `service.respond_to?(:mirror)`, and `Blob#service` resolves from the row's own `service_name`, which still holds the pre-switch service. Enqueue the job directly: `ActiveStorage::MirrorJob.perform_later(blob.key, checksum: blob.checksum)`.
- Blobs written while Mirror was configured carry `service_name: "mirror"`. `Blob#service` is `services.fetch(service_name)`, so deleting the `mirror:` entry raises `KeyError` on every one of them. Before dropping it: `ActiveStorage::Blob.where(service_name: "mirror").update_all(service_name: "amazon")`.

No model or dual-read changes are needed beyond those two.

## Output Format

One block per attachment declaration - a model with both a `has_one_attached` and a `has_many_attached` emits two. In review mode, precede the blocks with numbered findings citing the violated rule; the block describes the corrected attachment, so target state lives there. Mark non-compliant fields `- GAP`, and any field whose evidence is outside the reviewed files `not in evidence` plus the file to read.

```
Attachment: <model>.<has_one_attached | has_many_attached :name>

Service: <amazon | google | azure | disk - reason>

Direct upload: <Yes (>1 MB expected) | No (small files only) | not in evidence>

Validation: <content_type allowlist | size limit | magic-byte sniff | post-attach valid? + purge - list all that apply>

Variants: <list with sizes | none | conditional on blob.image? (mixed-type attachment)>

Variant warming: <lazy | background job | not in evidence>

Processor: <vips (default, 7.0+) | mini_magick - reason | not configured - compliant>

Purge: <purge_later (default) | purge method in a rake/admin script | dependent: false - GAP>

Orphan cleanup: <scheduled rake | none - GAP when direct upload is Yes | n/a (no direct upload)>

Retention: <business rule + the state-transition timestamp it keys on + scheduled job | indefinite (stated) | none (GAP for regulated data)>

Access: <signed URL default | controller-gated + per-call expiry (any private file, staff or customer) | proxy mode behind CDN (high-traffic, authorization still at the controller)>

Migration: <none | from <uploader> - step N of 7 | service move via MirrorService>
```

Previews are warmed in the same job as variants, so `Variant warming` has no separate preview value. When the retention rule keys on a state transition the model does not record, say so - the timestamp column is part of the deliverable.

## Avoid

- Large uploads proxied through Puma without `direct_upload: true`
- Trusting client-supplied `content_type` for sensitive files
- `dependent:` set to anything but `:purge_later` or `false` - Rails honours no other value and silently skips the purge
- Lazy variants on high-traffic pages
- ImageMagick for new projects
- Leaking unsigned blob URLs to clients
- Hard-coded bucket names in models
- Forgetting orphan cleanup for abandoned direct uploads
