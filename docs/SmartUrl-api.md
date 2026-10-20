# Smart URL Processor API Documentation

## Overview

This document outlines the API endpoints for the Smart URL Processor service. The system provides intelligent URL processing with AI-powered link analysis, supporting:

1. **User Management**
   1. Create user accounts (username/password or Google OAuth)
   2. Login and logout via JWT authentication
   3. Manage user profile information

2. **Short URLs**
   1. Create short URLs from long ones with automatic title extraction
   2. Redirect from short URLs to their original destinations

3. **QR Codes**
   1. Generate QR codes from URLs with automatic title extraction
   2. Get QR code images (generated on demand)
   3. Redirect from QR codes to their original destinations

4. **AI Smart Analysis**
   1. Automatic link classification and categorization
   2. Malicious/spam URL detection via Hugging Face, OpenAI, and Google Safe Browsing API

5. **History**
   1. View paginated history of URLs created by a user
   2. View paginated history of QR codes created by a user

6. **Analytics**
   1. Track clicks and scans over time
   2. Track usage by device type and country
   3. Access aggregated analytics data for visualization

Each resource (URL, QR code) automatically extracts and stores the title of the target website. All URLs are analyzed by the AI module for safety and classification before being made available.

## API Endpoints

### 1. User Management Endpoints

#### 1.1. Register User (Username/Password)

**Purpose:** Create a new user account with username and password.

**Endpoint:** `/auth/register`

**Method:** `POST`

**Request Body:**
```json
{
  "username": "johndoe",
  "email": "john@example.com",
  "password": "securepassword123"
}
```

**Response:** (201 Created)
```json
{
  "id": 1,
  "username": "johndoe",
  "email": "john@example.com",
  "created_at": "2025-12-15T14:30:00Z"
}
```

**Error Responses:**
- 400 Bad Request: Invalid input (missing fields, invalid email format)
- 409 Conflict: Username or email already exists

#### 1.2. Register with Google

**Purpose:** Create a new user account or log in with Google authentication.

**Endpoint:** `/auth/google`

**Method:** `POST`

**Request Body:**
```json
{
  "token": "google_oauth_token"
}
```

**Response:** (201 Created)
```json
{
  "id": 2,
  "username": "janedoe",
  "email": "jane@example.com",
  "created_at": "2025-12-15T14:35:00Z",
  "auth_provider": "google"
}
```

#### 1.3. Login (Username/Password)

**Purpose:** Authenticate user and get JWT access token and refresh token.

**Endpoint:** `/auth/login`

**Method:** `POST`

**Request Body:**
```json
{
  "username": "johndoe",
  "password": "securepassword123"
}
```

**Response:** (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": 1,
    "username": "johndoe",
    "email": "john@example.com"
  }
}
```

**Error Responses:**
- 401 Unauthorized: Invalid username or password

#### 1.4. Refresh Token

**Purpose:** Get a new access token using a refresh token.

**Endpoint:** `/auth/refresh`

**Method:** `POST`

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:** (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### 1.5. Logout (Client-side)

**Purpose:** Client removes tokens from storage. No server-side action required with pure JWT.

**Note:** In a pure JWT implementation, logout is handled client-side by removing the tokens from storage. The frontend application should delete both the access token and refresh token from localStorage or cookies when the user logs out, and then redirect to the login page.

#### 1.6. Get User Profile

**Purpose:** Retrieve current user profile information.

**Endpoint:** `/users/me`

**Method:** `GET`

**Headers:**
- Authorization: Bearer {access_token}

**Response:** (200 OK)
```json
{
  "id": 1,
  "username": "johndoe",
  "email": "john@example.com",
  "created_at": "2025-12-15T14:30:00Z",
  "stats": {
    "urls_created": 15,
    "qr_codes_created": 8
  }
}
```

#### 1.7. Update User Profile

**Purpose:** Update user profile information.

**Endpoint:** `/users/me`

**Method:** `PATCH`

**Headers:**
- Authorization: Bearer {access_token}

**Request Body:**
```json
{
  "username": "johndoe_new",
  "email": "new_email@example.com"
}
```

**Response:** (200 OK)
```json
{
  "id": 1,
  "username": "johndoe_new",
  "email": "new_email@example.com",
  "created_at": "2025-12-15T14:30:00Z"
}
```

### 2. Short URL Endpoints

#### 2.1. Create Short URL

**Purpose:** Convert a long URL into a short URL with a randomly generated code. Automatically extracts website title and runs AI safety/classification analysis.

**Endpoint:** `/shorten/`

**Method:** `POST`

**Headers:**
- Authorization: Bearer {access_token}

**Request Body:**
```json
{
  "target_url": "https://example.com/your/long/url"
}
```

**Response:** (201 Created)
```json
{
  "original_url": "https://example.com/your/long/url",
  "short_code": "abc123",
  "short_url": "http://localhost:8000/abc123",
  "title": "Example Website Homepage",
  "clicks": 0,
  "user_id": 1,
  "ai_analysis": {
    "category": "technology",
    "is_safe": true,
    "safety_score": 0.98,
    "checked_at": "2025-12-15T14:30:00Z"
  },
  "created_at": "2025-12-15T14:30:00Z"
}
```

**Error Responses:**
- 400 Bad Request: Invalid URL format
- 403 Forbidden: URL flagged as malicious by AI analysis

**Note:** The AI analysis runs asynchronously via the message queue. If the analysis is still pending at the time of response, `ai_analysis` will be `null` and the result will be available via the AI analysis endpoint.

#### 2.2. Redirect from Short URL

**Purpose:** Redirect visitors to the original URL when they use a short link.

**Endpoint:** `/{short_code}`

**Method:** `GET`

**Example:**
- When someone visits `http://localhost:8000/abc123`
- They are redirected to the original URL
- The click counter is incremented
- An analytics event is recorded asynchronously via the message queue

**Response:**
- 307 Temporary Redirect to the original URL
- 404 Not Found if the short code doesn't exist
- 403 Forbidden if the URL has been flagged as unsafe

### 3. QR Code Endpoints

#### 3.1. Generate QR Code

**Purpose:** Create a QR code from a URL. Automatically extracts website title and runs AI safety/classification analysis.

**Endpoint:** `/qrcode/`

**Method:** `POST`

**Headers:**
- Authorization: Bearer {access_token}

**Request Body:**
```json
{
  "target_url": "https://example.com/your/long/url"
}
```

**Response:** (201 Created)
```json
{
  "original_url": "https://example.com/your/long/url",
  "qr_code_id": "qr123",
  "qr_code_url": "http://localhost:8000/qrcode/qr123",
  "title": "Example Website Homepage",
  "scans": 0,
  "user_id": 1,
  "ai_analysis": {
    "category": "technology",
    "is_safe": true,
    "safety_score": 0.98,
    "checked_at": "2025-12-15T14:30:00Z"
  },
  "created_at": "2025-12-15T14:30:00Z"
}
```

#### 3.2. Get QR Code Image

**Purpose:** Retrieve the generated QR code image.

**Endpoint:** `/qrcode/{qr_code_id}/image`

**Method:** `GET`

**Response:**
- QR code image (PNG format)
- 404 Not Found if the QR code ID doesn't exist

#### 3.3. Redirect from QR Code

**Purpose:** Redirect visitors to the original URL when they scan a QR code.

**Endpoint:** `/qrcode/{qr_code_id}`

**Method:** `GET`

**Example:**
- When someone scans a QR code that leads to `http://localhost:8000/qrcode/qr123`
- The scan counter is incremented
- An analytics event is recorded asynchronously via the message queue
- They are redirected to the original URL

**Response:**
- 307 Temporary Redirect to the original URL
- 404 Not Found if the QR code ID doesn't exist
- 403 Forbidden if the URL has been flagged as unsafe

### 4. AI Analysis Endpoints

#### 4.1. Get AI Analysis for a URL

**Purpose:** Retrieve the AI safety and classification analysis result for a specific short URL.

**Endpoint:** `/ai/analysis/url/{short_code}`

**Method:** `GET`

**Headers:**
- Authorization: Bearer {access_token}

**Response:** (200 OK)
```json
{
  "short_code": "abc123",
  "original_url": "https://example.com/your/long/url",
  "analysis": {
    "category": "technology",
    "is_safe": true,
    "safety_score": 0.98,
    "threat_types": [],
    "ai_provider": "openai",
    "google_safe_browsing": {
      "is_safe": true,
      "threat_types": []
    },
    "checked_at": "2025-12-15T14:30:00Z"
  }
}
```

#### 4.2. Get AI Analysis for a QR Code

**Purpose:** Retrieve the AI safety and classification analysis result for a specific QR code.

**Endpoint:** `/ai/analysis/qrcode/{qr_code_id}`

**Method:** `GET`

**Headers:**
- Authorization: Bearer {access_token}

**Response:** (200 OK)
```json
{
  "qr_code_id": "qr123",
  "original_url": "https://example.com/your/long/url",
  "analysis": {
    "category": "technology",
    "is_safe": true,
    "safety_score": 0.98,
    "threat_types": [],
    "ai_provider": "huggingface",
    "google_safe_browsing": {
      "is_safe": true,
      "threat_types": []
    },
    "checked_at": "2025-12-15T14:30:00Z"
  }
}
```

#### 4.3. Re-analyze a URL

**Purpose:** Trigger a re-analysis of a URL (useful if the target content may have changed).

**Endpoint:** `/ai/reanalyze/{resource_type}/{resource_id}`

**Method:** `POST`

**Headers:**
- Authorization: Bearer {access_token}

**Path Parameters:**
- `resource_type`: `url` or `qrcode`
- `resource_id`: The short_code or qr_code_id

**Response:** (202 Accepted)
```json
{
  "message": "Re-analysis queued",
  "resource_type": "url",
  "resource_id": "abc123",
  "queued_at": "2025-12-15T16:00:00Z"
}
```

**Note:** Re-analysis is processed asynchronously via RabbitMQ/Kafka. The updated result will be available via the analysis endpoints once processing is complete.

### 5. History Endpoints

#### 5.1. Get URL History

**Purpose:** Retrieve all shortened URLs created by the current user with pagination.

**Endpoint:** `/urls/history`

**Method:** `GET`

**Headers:**
- Authorization: Bearer {access_token}

**Query Parameters:**
- `page=1` - Page number for pagination (default: 1)
- `limit=20` - Number of items per page (default: 20)
- `sort=created_at|clicks` - Sort field (default: created_at)
- `order=asc|desc` - Sort order (default: desc)

**Response:** (200 OK)
```json
{
  "page": 1,
  "limit": 20,
  "total": 35,
  "urls": [
    {
      "original_url": "https://example.com/your/long/url",
      "short_code": "abc123",
      "short_url": "http://localhost:8000/abc123",
      "title": "Example Website Homepage",
      "clicks": 42,
      "is_safe": true,
      "category": "technology",
      "created_at": "2025-12-15T14:30:00Z"
    }
  ]
}
```

#### 5.2. Get QR Code History

**Purpose:** Retrieve all QR codes created by the current user with pagination.

**Endpoint:** `/qrcodes/history`

**Method:** `GET`

**Headers:**
- Authorization: Bearer {access_token}

**Query Parameters:**
- `page=1` - Page number for pagination (default: 1)
- `limit=20` - Number of items per page (default: 20)
- `sort=created_at|scans` - Sort field (default: created_at)
- `order=asc|desc` - Sort order (default: desc)

**Response:** (200 OK)
```json
{
  "page": 1,
  "limit": 20,
  "total": 22,
  "qrcodes": [
    {
      "original_url": "https://example.com/your/long/url",
      "qr_code_id": "qr123",
      "qr_code_url": "http://localhost:8000/qrcode/qr123",
      "title": "Example Website Homepage",
      "scans": 35,
      "is_safe": true,
      "category": "technology",
      "created_at": "2025-12-15T14:30:00Z"
    }
  ]
}
```

### 6. Analytics Endpoints

#### 6.1. Get Short URL Analytics

**Purpose:** Retrieve analytics data for a specific short URL.

**Endpoint:** `/analytics/url/{short_code}`

**Method:** `GET`

**Headers:**
- Authorization: Bearer {access_token}

**Response:** (200 OK)
```json
{
  "original_url": "https://example.com/your/long/url",
  "short_code": "abc123",
  "short_url": "http://localhost:8000/abc123",
  "title": "Example Website Homepage",
  "created_at": "2025-12-15T14:30:00Z",
  "owner": {
    "id": 1,
    "username": "johndoe"
  },
  "clicks": 42,
  "click_data": {
    "daily": [
      {"date": "2025-12-15", "clicks": 10},
      {"date": "2025-12-16", "clicks": 15},
      {"date": "2025-12-17", "clicks": 17}
    ],
    "devices": [
      {"type": "desktop", "count": 25},
      {"type": "mobile", "count": 15},
      {"type": "tablet", "count": 2}
    ],
    "countries": [
      {"country": "United States", "count": 20},
      {"country": "Canada", "count": 12},
      {"country": "United Kingdom", "count": 10}
    ]
  }
}
```

#### 6.2. Get QR Code Analytics

**Purpose:** Retrieve analytics data for a specific QR code.

**Endpoint:** `/analytics/qrcode/{qr_code_id}`

**Method:** `GET`

**Headers:**
- Authorization: Bearer {access_token}

**Response:** (200 OK)
```json
{
  "original_url": "https://example.com/your/long/url",
  "qr_code_id": "qr123",
  "qr_code_url": "http://localhost:8000/qrcode/qr123",
  "title": "Example Website Homepage",
  "created_at": "2025-12-15T14:30:00Z",
  "owner": {
    "id": 1,
    "username": "johndoe"
  },
  "scans": 35,
  "scan_data": {
    "daily": [
      {"date": "2025-12-15", "scans": 8},
      {"date": "2025-12-16", "scans": 12},
      {"date": "2025-12-17", "scans": 15}
    ],
    "devices": [
      {"type": "desktop", "count": 10},
      {"type": "mobile", "count": 20},
      {"type": "tablet", "count": 5}
    ],
    "countries": [
      {"country": "United States", "count": 18},
      {"country": "Canada", "count": 10},
      {"country": "United Kingdom", "count": 7}
    ]
  }
}
```

#### 6.3. Get Aggregated Analytics

**Purpose:** Retrieve aggregated analytics across all URLs and QR codes for the current user.

**Endpoint:** `/analytics/summary`

**Method:** `GET`

**Headers:**
- Authorization: Bearer {access_token}

**Query Parameters:**
- `period=day|week|month|year` - Time period for analytics (default: month)
- `start_date=YYYY-MM-DD` - Start date for custom range (optional)
- `end_date=YYYY-MM-DD` - End date for custom range (optional)

**Response:** (200 OK)
```json
{
  "period": "month",
  "start_date": "2025-11-17",
  "end_date": "2025-12-17",
  "total_urls": 125,
  "total_qrcodes": 84,
  "total_clicks": 3542,
  "total_qr_scans": 1846,
  "daily_activity": [
    {
      "date": "2025-12-17",
      "clicks": 152,
      "qr_scans": 87
    }
  ],
  "top_urls": [
    {
      "short_code": "abc123",
      "original_url": "https://example.com/popular-page",
      "title": "Popular Example Page",
      "clicks": 328
    }
  ],
  "top_qrcodes": [
    {
      "qr_code_id": "qr789",
      "original_url": "https://example.com/popular-qr-page",
      "title": "Popular QR Page",
      "scans": 187
    }
  ]
}
```

## Environment Variables

The application requires the following environment variables to be set:

| Variable | Description | Default |
|----------|-------------|---------|
| DB_NAME | PostgreSQL database name | smart_url_processor |
| DB_USER | PostgreSQL username | postgres |
| DB_PASSWORD | PostgreSQL password | postgres |
| DB_HOST | PostgreSQL host | localhost |
| DB_PORT | PostgreSQL port | 5432 |
| JWT_SECRET | Secret key for signing JWTs | None |
| JWT_ACCESS_EXPIRE | Access token expiration in seconds | 3600 (1 hour) |
| JWT_REFRESH_EXPIRE | Refresh token expiration in seconds | 604800 (7 days) |
| REDIS_HOST | Redis server host | localhost |
| REDIS_PORT | Redis server port | 6379 |
| RABBITMQ_URL | RabbitMQ connection URL | amqp://guest:guest@localhost:5672 |
| GOOGLE_CLIENT_ID | Google OAuth client ID | None |
| GOOGLE_CLIENT_SECRET | Google OAuth client secret | None |
| OPENAI_API_KEY | OpenAI API key for AI analysis | None |
| HUGGINGFACE_API_KEY | Hugging Face API key for AI analysis | None |
| GOOGLE_SAFE_BROWSING_KEY | Google Safe Browsing API key | None |

## Website Title Extraction

The Smart URL Processor automatically extracts website titles when creating URLs and QR codes:

- When a user submits a URL, the system makes a request to the target website
- The HTML is parsed to extract the `<title>` tag content
- This title is stored in the database and returned in API responses
- If extraction fails (network issues, invalid URL, missing title), the title field will be null
- No additional input is required from users for this feature

## AI Analysis Pipeline

When a new URL or QR code is created, the system performs intelligent analysis:

1. **URL Submission** — The URL is submitted to the message queue (RabbitMQ/Kafka) for async processing
2. **Google Safe Browsing Check** — The URL is checked against Google's Safe Browsing database for known threats
3. **AI Classification** — Hugging Face and/or OpenAI models classify the URL content into categories (technology, education, shopping, news, etc.)
4. **Safety Scoring** — A composite safety score (0.0 - 1.0) is calculated based on all analysis results
5. **Result Storage** — The analysis result is stored in the database and cached in Redis
6. **Flagging** — URLs with safety scores below the threshold are flagged and may be blocked from redirecting

If a URL is flagged as malicious, users attempting to access the short link or QR code will receive a 403 Forbidden response instead of being redirected.

## Caching Strategy

The system uses Redis caching to optimize performance:

- **Hot link caching**: Frequently accessed short URLs and QR codes are cached in Redis to reduce database lookups
- **AI analysis results**: Analysis results are cached to avoid redundant API calls
- **Cache invalidation**: Cache entries are invalidated when resources are updated or re-analyzed
- **TTL**: Cached entries have a configurable time-to-live to ensure eventual consistency
