---
name: rails-active-storage-patterns
description: "Active Storage on Rails 7.2: direct S3/GCS upload, libvips variants, background processing, purge_later, CarrierWave/Paperclip migration."
metadata:
  category: backend
  tags: [ruby, rails, active-storage, s3, upload, attachments]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the storage service (S3/GCS/Azure/disk) and image processor (libvips/ImageMagick).

## When to Use

- Adding file or image uploads to a model
- Configuring direct upload to avoid proxying through the app
- Designing variant/preview processing pipelines
- Purging attachments on parent destroy
- Migrating from CarrierWave, Paperclip, or Shrine to Active Storage
- Reviewing upload security (content-type, size, signed URL exposure)

## Rules

- Direct upload (`direct_upload: true` on `file_field`) for files >1 MB - proxying through Puma blocks a worker for the upload duration.
- One Active Storage service per environment in `config/storage.yml`; reference by symbol in `config.active_storage.service`. Never hard-code bucket names in models.
- `has_one_attached` / `has_many_attached` with `dependent: :purge_later` so destroying the parent enqueues blob deletion (avoid `:purge` - synchronous, blocks the request).
- Use **libvips** (`config.active_storage.variant_processor = :vips`) - 4-10x faster and lower memory than ImageMagick. Install `libvips` system package; gem `image_processing`.
- Validate `content_type` and `byte_size` in the model with `validate` callbacks or `active_storage_validations` gem - Active Storage itself does no validation.
- Signed URLs (`rails_blob_url` / `url_for`) expire after `ActiveStorage.urls_expire_in` (default 5 min) - tune per use case; never expose unsigned blob keys to clients.
- Variants are lazy by default - first request blocks rendering. Use `variant(...).processed.url` in a background job or `preview` with a job that warms the variant.
- Multi-DB apps: Active Storage tables live on the primary by default. Use `connects_to` in `ActiveStorage::Record` only if `active_storage` is intentionally on a separate DB.

## Patterns

### Direct Upload to S3/GCS

```ruby
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

The form posts the file metadata to `/rails/active_storage/direct_uploads`, receives a signed PUT URL, uploads directly to S3, then submits the form with the resulting `signed_id`. Puma sees only the small metadata roundtrip.

Configure CORS on the bucket - direct upload PUTs from the browser need:

```
AllowedOrigins: https://app.example.com
AllowedMethods: PUT, POST
AllowedHeaders: Content-Type, Content-MD5, Content-Disposition, x-amz-acl, Origin
```

### Validation

```ruby
class User < ApplicationRecord
  has_one_attached :avatar, dependent: :purge_later

  validate :avatar_constraints

  AVATAR_TYPES = %w[image/jpeg image/png image/webp].freeze
  AVATAR_MAX_BYTES = 5.megabytes

  private

  def avatar_constraints
    return unless avatar.attached?
    errors.add(:avatar, "must be JPEG, PNG, or WebP") unless AVATAR_TYPES.include?(avatar.content_type)
    errors.add(:avatar, "must be <= 5 MB")            if avatar.byte_size > AVATAR_MAX_BYTES
  end
end
```

Or use `active_storage_validations`:

```ruby
has_one_attached :avatar, dependent: :purge_later
validates :avatar, content_type: AVATAR_TYPES, size: { less_than: 5.megabytes }
```

`content_type` is client-supplied unless re-verified - for sensitive uploads, sniff the magic bytes server-side (`Marcel::MimeType.for`).

### Variants

```ruby
class User < ApplicationRecord
  has_one_attached :avatar do |attachable|
    attachable.variant :thumb,  resize_to_fill: [80, 80]
    attachable.variant :medium, resize_to_fill: [320, 320]
  end
end
```

Rendering:

```erb
<%# Lazy - first request triggers processing inline %>
<%= image_tag user.avatar.variant(:thumb) %>

<%# Warmed - background job processes; URL is stable %>
<%= image_tag user.avatar.variant(:thumb).processed %>
```

For high-traffic display paths, dispatch a job on attachment that calls `.processed` for each declared variant. Otherwise the first cold view pays the processing cost.

### Background Processing

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

Dispatch from the controller after `record.save!` and the signed_id is known. The controller responds immediately; the user sees the placeholder until the variant is ready (poll, Turbo Stream, or websocket).

### Purge Semantics

| Method               | Behavior                                      | Use when                              |
| -------------------- | --------------------------------------------- | ------------------------------------- |
| `attachment.purge`   | Sync delete blob + variants                   | Rake/admin scripts; OK if blocking    |
| `attachment.purge_later` | Enqueue `ActiveStorage::PurgeJob`         | Default; non-blocking                 |
| `dependent: :purge_later` | On parent destroy, enqueue purge jobs    | All model attachments                 |
| `dependent: :purge`  | On parent destroy, sync purge (blocks)        | Avoid in request path                 |

Detached blobs (created via direct upload but never attached) become orphans. Schedule `ActiveStorage::PurgeJob` for blobs older than 1 day with no attachments:

```ruby
ActiveStorage::Blob.unattached.where("created_at < ?", 1.day.ago).find_each(&:purge_later)
```

### Migrating from CarrierWave/Paperclip

1. Add Active Storage tables (`bin/rails active_storage:install` + migrate).
2. Keep the old uploader in place. Add `has_one_attached :new_<name>` on the model.
3. Backfill rake task: for each record, download from the old uploader URL, attach to the new association.
4. Read path: `record.new_<name>.attached? ? record.new_<name> : record.<name>` - dual-read during transition.
5. Switch writes to Active Storage only. Backfill stragglers.
6. Drop the old column and uploader once read traffic is 0 on the legacy path.

Plan a rollback: keep the old data until the new attachments are verified.

## Output Format

When designing or reviewing an attachment:

```
Attachment: <model>.<has_one_attached/has_many_attached :name>
Service: <amazon | google | azure | disk - reason>
Direct upload: <Yes (>1 MB expected) | No (small files only)>
Validation: <content_type allowlist | size limit | magic-byte sniff>
Variants: <list with sizes | none>
Variant warming: <lazy | background job | preview job>
Processor: <vips | mini_magick - reason>
Purge: <purge_later (default) | purge (justified)>
Orphan cleanup: <scheduled rake | none (GAP)>
```

## Avoid

- Proxying large uploads through Puma without `direct_upload: true` - blocks workers for upload duration
- Trusting client-supplied `content_type` for sensitive files - sniff magic bytes server-side
- `dependent: :purge` on hot-path models - sync delete blocks the response
- Lazy variants on high-traffic pages - first-view latency spike per variant
- ImageMagick for new projects - libvips is faster, lower memory, fewer CVEs
- Leaking unsigned blob URLs to clients - always use `rails_blob_url` / `url_for` with expiry
- Hard-coding bucket names in models - violates env separation
- Forgetting orphan cleanup - direct upload abandons accumulate as unattached blobs
