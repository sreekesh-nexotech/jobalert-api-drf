# JobAlert API — Endpoint Reference

**Base URL:** `http://<host>/api/v1/`
**Auth:** JWT (SimpleJWT). All non-public endpoints require `Authorization: Bearer <access_token>`.
**Resource lookup:** by `uid` (UUID) — never internal `id`.
**Schema / Docs:** `/api/schema/`, `/api/docs/`, `/api/redoc/`.

## Common Headers

| Header | Value |
|---|---|
| `Content-Type` | `application/json` (or `multipart/form-data` for file/avatar) |
| `Authorization` | `Bearer <access_token>` (auth-required endpoints) |
| `Accept` | `application/json` |

## Common Query Parameters (list endpoints)

| Param | Description |
|---|---|
| `page` | Page number (paginated endpoints) |
| `page_size` | Items per page |
| `search` | Free-text search on indexed fields |
| `ordering` | Field to order by, prefix `-` for desc |

---

# Auth

## POST `/auth/register/`
Public. Creates a user, issues JWT pair, and triggers a signup OTP email (best-effort).

**Headers:** `Content-Type: application/json`

**Request:**
```json
{
  "email": "user@example.com",
  "username": "user1",
  "password": "Strongpass123!",
  "password_confirm": "Strongpass123!",
  "first_name": "First",
  "last_name": "Last",
  "country_code": "+91",
  "mobile_number": "9876543210"
}
```

**Response 201:**
```json
{
  "user": {
    "uid": "uuid",
    "email": "user@example.com",
    "username": "user1",
    "first_name": "First",
    "last_name": "Last",
    "country_code": "+91",
    "mobile_number": "9876543210",
    "is_active": true,
    "date_joined": "2026-05-07T10:00:00Z",
    "last_login": null
  },
  "access": "<jwt>",
  "refresh": "<jwt>",
  "otp_sent": true
}
```

---

## POST `/auth/login/`
Public. Login with email **or** mobile number.

**Headers:** `Content-Type: application/json`

**Request (email):**
```json
{
  "identifier": "user@example.com",
  "password": "Strongpass123!"
}
```

**Request (mobile):**
```json
{
  "identifier": "9876543210",
  "country_code": "+91",
  "password": "Strongpass123!"
}
```

**Response 200:**
```json
{
  "user": { "...": "UserSerializer" },
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```

---

## POST `/auth/refresh/`
Public. Refresh access token.

**Headers:** `Content-Type: application/json`

**Request:**
```json
{ "refresh": "<refresh_token>" }
```

**Response 200:**
```json
{ "access": "<new_access_token>" }
```

---

## POST `/auth/logout/`
Auth required. Blacklists the refresh token.

**Headers:** `Authorization: Bearer <access>`, `Content-Type: application/json`

**Request:**
```json
{ "refresh": "<refresh_token>" }
```

**Response:** `205 RESET_CONTENT` (no body)

---

## POST `/auth/change-password/`
Auth required.

**Headers:** `Authorization`, `Content-Type: application/json`

**Request:**
```json
{
  "old_password": "Oldpass123!",
  "new_password": "Newpass123!"
}
```

**Response:** `204 NO_CONTENT`

---

## POST `/auth/otp/send/`
Public. Throttled (`otp_send` scope). Always returns 200 (anti-enumeration).

**Headers:** `Content-Type: application/json`

**Request:**
```json
{
  "identifier": "user@example.com",
  "purpose": "signup_verify"
}
```
`purpose` ∈ `signup_verify`, `password_reset`.

**Response 200:**
```json
{ "sent": true }
```

---

## POST `/auth/otp/verify/`
Public.

**Headers:** `Content-Type: application/json`

**Request:**
```json
{
  "identifier": "user@example.com",
  "purpose": "signup_verify",
  "code": "123456"
}
```

**Response 200:**
```json
{ "verified": true }
```

---

## POST `/auth/password-reset/request/`
Public. Throttled. Always returns 200.

**Headers:** `Content-Type: application/json`

**Request:**
```json
{ "email": "user@example.com" }
```

**Response 200:**
```json
{ "sent": true }
```

---

## POST `/auth/password-reset/confirm/`
Public.

**Headers:** `Content-Type: application/json`

**Request:**
```json
{
  "email": "user@example.com",
  "code": "123456",
  "new_password": "Newpass123!"
}
```

**Response:** `204 NO_CONTENT`

---

# Users / Profile

## GET `/users/me/`
Auth required.

**Headers:** `Authorization`

**Response 200:**
```json
{
  "uid": "uuid",
  "email": "user@example.com",
  "username": "user1",
  "first_name": "First",
  "last_name": "Last",
  "country_code": "+91",
  "mobile_number": "9876543210",
  "is_active": true,
  "date_joined": "2026-05-07T10:00:00Z",
  "last_login": "2026-05-07T11:00:00Z"
}
```

## PATCH `/users/me/`
Auth required.

**Headers:** `Authorization`, `Content-Type: application/json`

**Request (any subset of writable fields):**
```json
{
  "username": "newname",
  "first_name": "New",
  "last_name": "Name",
  "country_code": "+91",
  "mobile_number": "9876543210"
}
```

**Response 200:** Same as GET.

---

## POST `/users/me/avatar/`
Auth required. Multipart upload.

**Headers:** `Authorization`, `Content-Type: multipart/form-data`

**Request (form-data):**
```
image: <file>
```

**Response 200:**
```json
{ "profile_picture_url": "https://host/media/avatars/<uid>.jpg" }
```

---

## GET `/users/me/stats/`
Auth required.

**Headers:** `Authorization`

**Response 200:**
```json
{
  "posts": 3,
  "saved": 12,
  "upvotes_given": 25,
  "points": 320,
  "points_level": "contributor",
  "next_level": "champion",
  "next_level_at": 500,
  "progress_pct": 64,
  "is_premium": false,
  "premium_expires_at": null
}
```

---

## POST `/users/me/request-deletion/`
Auth required. Soft-flags the account for deletion.

**Headers:** `Authorization`

**Response 200:**
```json
{
  "account_status": "deletion_requested",
  "deletion_requested_at": "2026-05-07T11:00:00Z"
}
```

---

# User Details (`/user-details/`)

Self for users, all rows for admin. Lookup by user UUID (`uid`).

## GET `/user-details/`
**Headers:** `Authorization`
**Response 200:** paginated list of `UserDetails`.

## GET `/user-details/{uid}/`
**Headers:** `Authorization`

**Response 200:**
```json
{
  "user": { "...": "UserSerializer" },
  "date_of_birth": "1995-04-01",
  "gender": "male",
  "state": "Tamil Nadu",
  "city": "Chennai",
  "profile_picture_url": "https://...",
  "job_preferences": ["Design", "Marketing"],
  "is_premium": false,
  "premium_expires_at": null,
  "account_status": "active",
  "deletion_requested_at": null,
  "total_points": 320,
  "points_level": "contributor",
  "total_posts": 3,
  "total_saved": 12,
  "total_upvotes_given": 25,
  "otp_verified": true,
  "created_at": "...",
  "updated_at": "..."
}
```

## POST `/user-details/`
**Headers:** `Authorization`, `Content-Type: application/json`

**Request:**
```json
{
  "date_of_birth": "1995-04-01",
  "gender": "male",
  "state": "Tamil Nadu",
  "city": "Chennai",
  "profile_picture_url": "https://...",
  "job_preferences": ["Design", "Marketing"]
}
```

## PUT/PATCH `/user-details/{uid}/`
Same writable fields as POST.

## DELETE `/user-details/{uid}/`
**Response:** `204`

---

# Job Listings (`/job-listings/`)

Auth required. Read = approved+non-expired (or your own). Write = create as PENDING; edit while PENDING; admin overrides.

**Filters (query params):** `status`, `is_expired`, `is_trending`, `is_new`, `is_featured`, `is_verified`, `experience_level`, `category`, `sub_category`, `location`, `salary_min`, `salary_max`, `deadline_after`, `posted_by`
**Search:** `title`, `description`, `category`, `sub_category`, `tags`
**Ordering:** `created_at`, `upvotes_count`, `comments_count`, `saves_count`, `views_count`

## GET `/job-listings/`
**Headers:** `Authorization`
**Response 200:** paginated list.

## GET `/job-listings/{uid}/`
**Response 200:**
```json
{
  "uid": "uuid",
  "posted_by": { "...": "UserSerializer" },
  "approved_by": { "...": "UserSerializer | null" },
  "title": "Senior Designer",
  "category": "Design",
  "sub_category": "Product",
  "qualification": "BDes",
  "description": "...",
  "location": "Chennai",
  "experience_level": "3-5_yrs",
  "salary_min": "800000.00",
  "salary_max": "1400000.00",
  "salary_display": "₹8L – ₹14L",
  "application_deadline": "2026-06-01",
  "source_name": "LinkedIn",
  "source_url": "https://...",
  "tags": ["#Design", "#FullTime"],
  "is_trending": false,
  "is_new": true,
  "is_featured": false,
  "is_verified": false,
  "thumbnail_url": "https://...",
  "image_2_url": "",
  "image_3_url": "",
  "image_4_url": "",
  "image_5_url": "",
  "status": "approved",
  "is_expired": false,
  "approved_at": "...",
  "upvotes_count": 0,
  "comments_count": 0,
  "saves_count": 0,
  "views_count": 0,
  "created_at": "...",
  "updated_at": "..."
}
```

## POST `/job-listings/`
**Headers:** `Authorization`, `Content-Type: application/json`

**Request:**
```json
{
  "title": "Senior Designer",
  "category": "Design",
  "sub_category": "Product",
  "qualification": "BDes",
  "description": "...",
  "location": "Chennai",
  "experience_level": "3-5_yrs",
  "salary_min": "800000.00",
  "salary_max": "1400000.00",
  "salary_display": "₹8L – ₹14L",
  "application_deadline": "2026-06-01",
  "source_name": "LinkedIn",
  "source_url": "https://...",
  "tags": ["#Design"],
  "thumbnail_url": "https://...",
  "image_2_url": "",
  "image_3_url": "",
  "image_4_url": "",
  "image_5_url": ""
}
```

## PUT/PATCH `/job-listings/{uid}/`
Same writable fields.

## DELETE `/job-listings/{uid}/`
**Response:** `204`

## POST `/job-listings/{uid}/upvote/`
**Response 201/200:** `{ "upvoted": true, "created": true }`

## DELETE `/job-listings/{uid}/upvote/`
**Response 204:** `{ "upvoted": false }`

## POST `/job-listings/{uid}/save/`
**Response 200:** `{ "saved": true }`

## DELETE `/job-listings/{uid}/save/`
**Response 204:** `{ "saved": false }`

## POST `/job-listings/{uid}/apply/`
**Response 200:** `{ "applied": true }`

## POST `/job-listings/{uid}/view/`
**Response 200:** `{ "views_count": 42 }`

## POST `/job-listings/{uid}/approve/`  *(admin only)*
**Request:** `{ "notes": "" }`
**Response 200:** the updated `JobListing`.

## POST `/job-listings/{uid}/reject/`  *(admin only)*
**Request:** `{ "notes": "" }`
**Response 200:** the updated `JobListing`.

---

# Biz Listings (`/biz-listings/`)

Same shape as Job Listings. Replace job-specific fields with biz fields.

**Filters:** `status`, `is_expired`, `is_trending`, `is_new`, `is_featured`, `is_verified`, `opportunity_type`, `category`, `sub_category`, `venue`, `investment_min`, `investment_max`, `closing_after`, `posted_by`
**Search/Ordering:** same fields as Job.

## GET `/biz-listings/` · GET `/biz-listings/{uid}/`

**Response 200 (detail):**
```json
{
  "uid": "uuid",
  "posted_by": { "...": "UserSerializer" },
  "approved_by": null,
  "title": "Coffee Franchise",
  "category": "F&B",
  "sub_category": "Cafe",
  "description": "...",
  "opportunity_type": "franchise",
  "venue": "Pan India",
  "investment_min": "2500000.00",
  "investment_max": "8000000.00",
  "investment_display": "₹25L – ₹80L",
  "date_info": "Ongoing",
  "closing_date": "2026-08-15",
  "source_name": "",
  "source_url": "",
  "tags": ["#Franchise"],
  "is_trending": false,
  "is_new": true,
  "is_featured": false,
  "is_verified": false,
  "thumbnail_url": "https://...",
  "image_2_url": "",
  "image_3_url": "",
  "image_4_url": "",
  "image_5_url": "",
  "status": "approved",
  "is_expired": false,
  "approved_at": null,
  "upvotes_count": 0,
  "comments_count": 0,
  "saves_count": 0,
  "views_count": 0,
  "created_at": "...",
  "updated_at": "..."
}
```

## POST `/biz-listings/`
**Request:**
```json
{
  "title": "Coffee Franchise",
  "category": "F&B",
  "sub_category": "Cafe",
  "description": "...",
  "opportunity_type": "franchise",
  "venue": "Pan India",
  "investment_min": "2500000.00",
  "investment_max": "8000000.00",
  "investment_display": "₹25L – ₹80L",
  "date_info": "Ongoing",
  "closing_date": "2026-08-15",
  "source_name": "",
  "source_url": "",
  "tags": ["#Franchise"],
  "thumbnail_url": "https://...",
  "image_2_url": "",
  "image_3_url": "",
  "image_4_url": "",
  "image_5_url": ""
}
```

## PUT/PATCH `/biz-listings/{uid}/` · DELETE `/biz-listings/{uid}/`
Same shape as POST.

## POST/DELETE `/biz-listings/{uid}/upvote/`
## POST/DELETE `/biz-listings/{uid}/save/`
## POST `/biz-listings/{uid}/apply/`
## POST `/biz-listings/{uid}/view/`
## POST `/biz-listings/{uid}/approve/`  *(admin only)*
## POST `/biz-listings/{uid}/reject/`  *(admin only)*

Same payload/response shapes as the corresponding Job listing endpoints.

---

# Listings — Submission Gate

## GET `/listings/can-submit/`
Auth required.

**Headers:** `Authorization`

**Response 200:**
```json
{
  "can_submit": false,
  "pending_listing_type": "job",
  "pending_listing_uid": "uuid",
  "pending_title": "Senior Designer",
  "pending_submitted_at": "2026-05-07T11:00:00Z"
}
```

---

# Files (`/files/`)

Auth required. Owners (or admin) only.

**Filters:** `file_type`, `job_listing`, `biz_listing`, `user`
**Search:** `file_name`, `description`

## GET `/files/` · GET `/files/{uid}/`
**Response 200 (detail):**
```json
{
  "uid": "uuid",
  "listing_uid": "uuid|null",
  "file_name": "resume.pdf",
  "file_url": "https://...",
  "file_type": "pdf",
  "mime_type": "application/pdf",
  "file_size_bytes": 12345,
  "description": "...",
  "uploaded_by": { "...": "UserSerializer" },
  "created_at": "..."
}
```

## POST `/files/`
**Headers:** `Authorization`, `Content-Type: application/json`

**Request:**
```json
{
  "listing_type": "job",
  "target_listing_uid": "uuid",
  "file_name": "resume.pdf",
  "file_url": "https://...",
  "file_type": "pdf",
  "mime_type": "application/pdf",
  "file_size_bytes": 12345,
  "description": ""
}
```
`file_type` ∈ `pdf`, `doc`, `xlsx`, `csv`, `ppt`, `other`.
`listing_type` + `target_listing_uid` optional, but must be supplied together.

## PUT/PATCH `/files/{uid}/` · DELETE `/files/{uid}/`

---

# Saved & Applied (`/saved-listings/`)

Auth required. Read-only list of the current user's saved/applied items.

**Filters:** `listing_type`, `is_saved`, `is_applied`, `job_listing`, `biz_listing`

## GET `/saved-listings/` · GET `/saved-listings/{id}/`
**Response 200 (item):**
```json
{
  "id": 1,
  "user": { "...": "UserSerializer" },
  "listing_type": "job",
  "listing_uid": "uuid",
  "is_saved": true,
  "is_applied": false,
  "saved_at": "...",
  "applied_at": null,
  "created_at": "...",
  "updated_at": "..."
}
```

---

# Upvotes (`/upvotes/`)

Auth required. Read-only list of the current user's upvotes. (Toggle via listing's `upvote` action.)

**Filters:** `listing_type`, `job_listing`, `biz_listing`

## GET `/upvotes/` · GET `/upvotes/{id}/`
**Response 200 (item):**
```json
{
  "id": 1,
  "user": { "...": "UserSerializer" },
  "listing_type": "job",
  "listing_uid": "uuid",
  "created_at": "..."
}
```

---

# Comments (`/comments/`)

Auth required. Owners or admin can edit/delete.

**Filters:** `listing_type`, `is_deleted`, `job_listing`, `biz_listing`, `parent_comment`
**Search:** `text`

## GET `/comments/` · GET `/comments/{uid}/`
**Response 200 (detail):**
```json
{
  "uid": "uuid",
  "user": { "...": "UserSerializer" },
  "listing_type": "job",
  "listing_uid": "uuid",
  "parent_comment": "uuid|null",
  "text": "Great post!",
  "is_deleted": false,
  "replies_count": 2,
  "likes_count": 3,
  "created_at": "...",
  "updated_at": "..."
}
```

## POST `/comments/`
**Request:**
```json
{
  "listing_type": "job",
  "target_listing_uid": "uuid",
  "parent_comment_uid": "uuid|null",
  "text": "Great post!"
}
```

## PUT/PATCH `/comments/{uid}/`
**Request:**
```json
{ "text": "Edited", "listing_type": "job", "target_listing_uid": "uuid" }
```

## DELETE `/comments/{uid}/`
Soft delete. **Response:** `204`

---

# Comment Likes

## POST `/comments/{uid}/like/`
**Headers:** `Authorization`

**Response 201/200:**
```json
{ "liked": true, "likes_count": 4, "created": true }
```

## DELETE `/comments/{uid}/like/`
**Response 204:**
```json
{ "liked": false, "likes_count": 3 }
```

---

# Points History (`/points/history/`)

Auth required. User sees own ledger; admin sees all. Read-only.

**Filters:** `transaction_type`, `reason`, `created_after`, `created_before`

## GET `/points/history/` · GET `/points/history/{id}/`
**Response 200 (item):**
```json
{
  "id": 1,
  "user": { "...": "UserSerializer" },
  "transaction_type": "earned",
  "reason": "listing_approved",
  "points": 50,
  "balance_after": 320,
  "listing_uid": "uuid|null",
  "notes": "",
  "created_at": "..."
}
```

---

# Subscriptions (`/subscriptions/`)

Auth required. User sees own; admin sees all.

**Filters:** `plan_type`, `payment_status`, `payment_gateway`, `is_auto_renew`

## GET `/subscriptions/` · GET `/subscriptions/{uid}/`
**Response 200 (detail):**
```json
{
  "uid": "uuid",
  "user": { "...": "UserSerializer" },
  "plan_type": "premium_monthly",
  "plan_display_name": "Premium Monthly — ₹99/mo",
  "amount": "99.00",
  "currency": "INR",
  "payment_status": "success",
  "payment_gateway": "Razorpay",
  "gateway_order_id": "...",
  "gateway_payment_id": "...",
  "gateway_signature": "...",
  "subscription_start": "...",
  "subscription_end": "...",
  "is_auto_renew": false,
  "created_at": "...",
  "updated_at": "..."
}
```

## POST `/subscriptions/`
**Request:**
```json
{
  "plan_type": "premium_monthly",
  "plan_display_name": "Premium Monthly — ₹99/mo",
  "amount": "99.00",
  "currency": "INR",
  "payment_gateway": "Razorpay",
  "gateway_order_id": "order_xyz",
  "is_auto_renew": false
}
```

## PUT/PATCH `/subscriptions/{uid}/` · DELETE `/subscriptions/{uid}/`

---

# Filter Preferences (`/filter-prefs/`)

Auth required. Upserted on POST per `(user, filter_context)`.

## GET `/filter-prefs/` · GET `/filter-prefs/{id}/`
**Response 200 (item):**
```json
{
  "id": 1,
  "user": { "...": "UserSerializer" },
  "filter_context": "job",
  "selected_categories": ["Design", "Marketing"],
  "selected_locations": ["Remote", "Bengaluru"],
  "selected_experience_levels": ["fresher", "1-3_yrs"],
  "selected_opportunity_types": [],
  "sort_preference": "most_recent",
  "search_query": "",
  "remote_only": false,
  "verified_only": false,
  "hide_expired": true,
  "created_at": "...",
  "updated_at": "..."
}
```

## POST `/filter-prefs/`
**Request:**
```json
{
  "filter_context": "job",
  "selected_categories": ["Design"],
  "selected_locations": ["Remote"],
  "selected_experience_levels": ["1-3_yrs"],
  "selected_opportunity_types": [],
  "sort_preference": "most_recent",
  "search_query": "",
  "remote_only": false,
  "verified_only": false,
  "hide_expired": true
}
```

## PUT/PATCH `/filter-prefs/{id}/` · DELETE `/filter-prefs/{id}/`

---

# App Meta (`/app-meta/`)

Public read; admin write.

**Filters:** `meta_type`, `target_platform`, `is_active`, `valid_at`
**Search:** `key`, `title`, `message`
**Ordering:** `priority`, `created_at`, `valid_from`

## GET `/app-meta/` · GET `/app-meta/{id}/`
**Response 200 (detail):**
```json
{
  "id": 1,
  "key": "summer_promo_2026",
  "meta_type": "announcement",
  "title": "Summer Promo",
  "message": "20% off!",
  "cta_label": "Learn more",
  "cta_url": "https://...",
  "target_platform": "all",
  "min_app_version": "1.2.0",
  "max_app_version": "",
  "is_active": true,
  "is_dismissible": true,
  "priority": 10,
  "valid_from": "...",
  "valid_until": "...",
  "extra_data": {},
  "created_by": { "...": "UserSerializer" },
  "created_at": "...",
  "updated_at": "..."
}
```

## POST `/app-meta/`  *(admin)*
**Request:**
```json
{
  "key": "summer_promo_2026",
  "meta_type": "announcement",
  "title": "Summer Promo",
  "message": "20% off!",
  "cta_label": "Learn more",
  "cta_url": "https://...",
  "target_platform": "all",
  "min_app_version": "1.2.0",
  "max_app_version": "",
  "is_active": true,
  "is_dismissible": true,
  "priority": 10,
  "valid_from": "2026-05-01T00:00:00Z",
  "valid_until": "2026-08-01T00:00:00Z",
  "extra_data": {}
}
```

## PUT/PATCH `/app-meta/{id}/` · DELETE `/app-meta/{id}/`  *(admin)*

---

# Activity Logs (`/activity-logs/`)

Auth required. Users may POST own events; only admin may list/retrieve.

**Filters:** `user`, `action_type`, `listing_type`, `device_type`, `job_listing`, `biz_listing`, `created_after`, `created_before`

## GET `/activity-logs/` · GET `/activity-logs/{id}/`  *(admin)*
**Response 200 (item):**
```json
{
  "id": 1,
  "user": { "...": "UserSerializer" },
  "action_type": "view_listing",
  "listing_type": "job",
  "listing_uid": "uuid|null",
  "ip_address": "1.2.3.4",
  "device_type": "android",
  "app_version": "1.4.0",
  "metadata": {},
  "created_at": "..."
}
```

## POST `/activity-logs/`
**Request:**
```json
{
  "action_type": "view_listing",
  "listing_type": "job",
  "target_listing_uid": "uuid",
  "device_type": "android",
  "app_version": "1.4.0",
  "metadata": {}
}
```

`action_type` ∈ `login`, `logout`, `signup`, `view_listing`, `save_listing`, `unsave_listing`, `upvote`, `unvote`, `mark_applied`, `post_comment`, `report_listing`, `submit_listing`, `profile_update`, `filter_change`, `search`, `share_listing`, `upgrade_premium`.

---

# Reports (`/reports/`)

Auth required. End users create + view own; admin manages.

**Filters:** `listing_type`, `reason`, `status`, `job_listing`, `biz_listing`

## GET `/reports/` · GET `/reports/{id}/`
**Response 200 (detail):**
```json
{
  "id": 1,
  "user": { "...": "UserSerializer" },
  "listing_type": "job",
  "listing_uid": "uuid",
  "reason": "spam",
  "status": "pending",
  "reviewer": null,
  "reviewer_notes": "",
  "reviewed_at": null,
  "created_at": "...",
  "updated_at": "..."
}
```

## POST `/reports/`
**Request:**
```json
{
  "listing_type": "job",
  "target_listing_uid": "uuid",
  "reason": "spam"
}
```
`reason` ∈ `incorrect_info`, `duplicate`, `spam`, `expired`, `other`.

## PUT/PATCH `/reports/{id}/` · DELETE `/reports/{id}/`  *(admin)*

## POST `/reports/{id}/review/`  *(admin)*
**Request:**
```json
{
  "status": "resolved",
  "reviewer_notes": "Removed listing."
}
```
`status` ∈ `pending`, `reviewed`, `resolved`, `dismissed`.

**Response 200:** updated report payload.

---

# Notifications (`/notifications/`)

Auth required. Read-only list/retrieve; actions for read-state.

## GET `/notifications/` · GET `/notifications/{uid}/`
**Response 200 (detail):**
```json
{
  "uid": "uuid",
  "notification_type": "listing_approved",
  "title": "Your listing was approved",
  "message": "Senior Designer is now live.",
  "link_url": "https://...",
  "related_job_listing_uid": "uuid|null",
  "related_biz_listing_uid": "uuid|null",
  "related_comment_uid": "uuid|null",
  "is_read": false,
  "read_at": null,
  "created_at": "..."
}
```

## GET `/notifications/unread-count/`
**Response 200:**
```json
{ "unread": 3 }
```

## POST `/notifications/{uid}/read/`
**Response 200:** the updated notification object.

## POST `/notifications/mark-all-read/`
**Response 200:**
```json
{ "ok": true }
```

---

# Static Pages (`/static-pages/`)

Public read (published only); admin write. Lookup by `slug`.

`slug` ∈ `privacy_policy`, `terms_of_service`, `help`, `about`.

## GET `/static-pages/` · GET `/static-pages/{slug}/`
**Response 200 (detail):**
```json
{
  "slug": "privacy_policy",
  "title": "Privacy Policy",
  "body": "...",
  "is_published": true,
  "version": 3,
  "updated_by": { "...": "UserSerializer" },
  "created_at": "...",
  "updated_at": "..."
}
```

## POST `/static-pages/`  *(admin)*
**Request:**
```json
{
  "slug": "privacy_policy",
  "title": "Privacy Policy",
  "body": "Markdown...",
  "is_published": true
}
```

## PUT/PATCH `/static-pages/{slug}/` · DELETE `/static-pages/{slug}/`  *(admin)*

---

# Home Feed

## GET `/home/feed/`
Auth required.

**Headers:** `Authorization`

**Response 200:**
```json
{
  "new_jobs_count": 8,
  "suggested_jobs": [ { "...": "JobListing" } ],
  "trending_biz":   [ { "...": "BizListing" } ],
  "unread_notifications": 3,
  "stats": {
    "posts": 3,
    "saved": 12,
    "upvotes_given": 25,
    "points": 320,
    "points_level": "contributor",
    "next_level": "champion",
    "next_level_at": 500,
    "progress_pct": 64,
    "is_premium": false,
    "premium_expires_at": null
  }
}
```

---

# Enum Reference

| Field | Values |
|---|---|
| `ListingStatus` | `pending`, `approved`, `rejected`, `expired` |
| `ListingType` / `listing_type` | `job`, `biz` |
| `Job.experience_level` | `fresher`, `1-3_yrs`, `3-5_yrs`, `5+_yrs` |
| `Biz.opportunity_type` | `franchise`, `investment`, `channel_partner`, `joint_venture`, `other` |
| `File.file_type` | `pdf`, `doc`, `xlsx`, `csv`, `ppt`, `other` |
| `UserDetails.gender` | `male`, `female`, `other`, `prefer_not_to_say` |
| `UserDetails.account_status` | `active`, `suspended`, `deletion_requested`, `deactivated` |
| `UserDetails.points_level` | `newcomer`, `contributor`, `champion`, `legend` |
| `OTP.purpose` | `signup_verify`, `password_reset` |
| `Notification.notification_type` | `listing_approved`, `listing_rejected`, `new_listing_match`, `comment_reply`, `points_earned`, `premium_expiring`, `announcement` |
| `Subscription.plan_type` | `free`, `premium_monthly`, `premium_yearly` |
| `Subscription.payment_status` | `initiated`, `success`, `failed`, `refunded`, `cancelled` |
| `FiltersMetaData.filter_context` | `job`, `biz` |
| `FiltersMetaData.sort_preference` | `most_recent`, `most_upvoted`, `salary_high`, `investment_low` |
| `AppMetaData.meta_type` | `announcement`, `update_warning`, `maintenance`, `promotional`, `home_banner` |
| `AppMetaData.target_platform` | `all`, `android`, `ios`, `web` |
| `PointsHistory.transaction_type` | `earned`, `redeemed`, `expired`, `adjusted` |
| `PointsHistory.reason` | `listing_approved`, `referral`, `profile_complete`, `daily_login`, `comment_posted`, `bonus`, `other` |
| `UserActivityLog.action_type` | `login`, `logout`, `signup`, `view_listing`, `save_listing`, `unsave_listing`, `upvote`, `unvote`, `mark_applied`, `post_comment`, `report_listing`, `submit_listing`, `profile_update`, `filter_change`, `search`, `share_listing`, `upgrade_premium` |
| `ListingReport.reason` | `incorrect_info`, `duplicate`, `spam`, `expired`, `other` |
| `ListingReport.status` | `pending`, `reviewed`, `resolved`, `dismissed` |
| `StaticPage.slug` | `privacy_policy`, `terms_of_service`, `help`, `about` |
