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
- `has_one_attached` / `has_many_attached` use `dependent: :purge_later`; reserve `:purge` for admin/rake scripts
- Validate `content_type` and `byte_size` in the model (or via `active_storage_validations`) - Active Storage does no validation itself
- Re-detect content type via magic bytes for sensitive uploads; client `content_type` is untrusted. Run it in the attach-time background job using `blob.open { |f| Marcel::MimeType.for(f) }` - streaming, not `blob.download` (loads the whole file into memory). Gate visibility on the result: a `verified_at`/quarantine flag holds the file from viewers until the sniff passes; purge on confirmed mismatch
- libvips processor (`config.active_storage.variant_processor = :vips`) - faster, lower memory, fewer CVEs than ImageMagick; install `libvips` + `image_processing` gem
- Variants are lazy by default; warm them in a background job for high-traffic paths
- Signed URLs only (`rails_blob_url` / `url_for`); never expose raw blob keys; tune `ActiveStorage.urls_expire_in`
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

Blob routes carry **no authorization** - anyone with a signed URL reads the file until it expires. For sensitive attachments: gate through your own controller (authorize, then redirect to a freshly signed URL), and shorten the window (`ActiveStorage.urls_expire_in` in minutes - e.g. 5 - for admin/underwriter viewing).

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

Non-image previews (PDF first page, video frame): `attachment.preview(resize_to_limit: [320, 320])` requires the system dependency (`poppler`/`mupdf` for PDF, `ffmpeg` for video) and only works when `attachment.previewable?`; guard rendering with `previewable?` and warm previews in the same background job as variants.

### Purge Semantics

| Method                       | Behavior                                   | Use when                              |
| ---------------------------- | ------------------------------------------ | ------------------------------------- |
| `attachment.purge`           | Sync delete blob + variants                | Rake/admin scripts                    |
| `attachment.purge_later`     | Enqueue `ActiveStorage::PurgeJob`          | Default; non-blocking                 |
| `dependent: :purge_later`    | On parent destroy, enqueue purge jobs      | All model attachments                 |
| `dependent: :purge`          | On parent destroy, sync purge (blocks)     | Avoid in request path                 |

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
3. Backfill rake: for each record, attach from the old storage. When source and target are the same S3 account (CW on S3), skip download-reupload: S3 server-side copy into the Active Storage key, then create the `ActiveStorage::Blob` row from the object's metadata (blobs need a base64-MD5 `checksum` - multipart ETags aren't MD5, so compute it once per object or copy single-part). Disk or cross-provider sources stream (`File.open` / `blob.open`) into `attach` - no copy shortcut. At millions of records, run as a sharded resumable backfill (`rails-work-splitter-patterns`).
4. Warm variants inside the backfill job (before reads flip), not lazily after.
5. Dual-read during transition (one helper/presenter owns it): `record.new_<name>.attached? ? record.new_<name> : record.<name>`.
6. Switch writes to Active Storage; backfill stragglers.
7. Drop the old column and uploader once legacy read traffic is 0.

Keep old data until new attachments are verified - plan the rollback. High-traffic public images: signed URLs rotate and bust CDN caches - use the proxy mode (`rails_storage_proxy_path`) behind a CDN, or a public bucket service, before flipping reads.

Already on Active Storage and only changing services (disk -> S3, bucket move)? Skip the steps above: configure `ActiveStorage::Service::MirrorService` (primary + mirror in `storage.yml`), let writes hit both, backfill old blobs with `blob.mirror_later` (or a rake loop), then flip primary and drop the mirror. No model or dual-read changes needed.

## Output Format

In review mode, precede the block with numbered findings citing the violated rule; mark non-compliant fields `- GAP`.

```
Attachment: <model>.<has_one_attached | has_many_attached :name>
Service: <amazon | google | azure | disk - reason>
Direct upload: <Yes (>1 MB expected) | No (small files only)>
Validation: <content_type allowlist | size limit | magic-byte sniff - list all that apply>
Variants: <list with sizes | none>
Variant warming: <lazy | background job | preview job>
Processor: <vips | mini_magick - reason>
Purge: <purge_later (default) | purge (justified)>
Orphan cleanup: <scheduled rake | none (GAP)>
Retention: <business rule + scheduled job | indefinite (stated) | none (GAP for regulated data)>
Access: <signed URL default | controller-gated + short expiry (sensitive) | proxy mode behind CDN (public high-traffic)>
```

## Avoid

- Large uploads proxied through Puma without `direct_upload: true`
- Trusting client-supplied `content_type` for sensitive files
- `dependent: :purge` on hot-path models
- Lazy variants on high-traffic pages
- ImageMagick for new projects
- Leaking unsigned blob URLs to clients
- Hard-coded bucket names in models
- Forgetting orphan cleanup for abandoned direct uploads
