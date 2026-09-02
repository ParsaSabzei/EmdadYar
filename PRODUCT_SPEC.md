# Emdadyar — MVP Product Specification

## 1. Overview

Emdadyar is a simple request-management system for a charity organization.

Beneficiaries use a Bale messenger bot to submit requests for different services.

Administrators use a simple web-based admin panel to:

* Create and manage services.
* Define the questions required for each service.
* View submitted requests.
* Change request statuses.
* Search for requests.
* Send text messages to beneficiaries.
* Delete requests.

The system should be intentionally simple.

Do not build unnecessary features, abstractions, dashboards, animations, complex UI, microservices, or enterprise architecture.

The priority is:

1. Correct functionality.
2. Simplicity.
3. Maintainability.
4. Low implementation complexity.

Visual design is not important.

---

# 2. Technology Stack

Use:

* Python
* FastAPI
* SQLAlchemy
* SQLite
* Jinja2 templates
* Plain HTML/CSS
* Bale Bot API
* Local filesystem for uploaded files

Do NOT use React, Vue, Angular, or another frontend framework.

Do NOT use PostgreSQL for the MVP.

The application should be a single simple backend application.

Use environment variables for secrets and configuration.

---

# 3. Users

There are only two types of users:

### Beneficiary

A person using the Bale bot.

The beneficiary does not need an account.

The beneficiary is identified by their Bale `chat_id`.

### Administrator

An administrator using the web panel.

All administrators have the same permissions.

There are no roles or permission levels.

For the MVP, administrators authenticate using username and password.

---

# 4. Beneficiary Identity

Do not create a complicated user/profile system.

The beneficiary is identified by:

```text
chat_id
```

A beneficiary may have multiple requests over time.

Do not create a separate profile-management feature.

The national ID is simply an answer to a form field when a service requires it.

---

# 5. Services

A service is a type of request.

Examples:

* Loan application
* Registration for a program
* Financial assistance
* Any other service created by an administrator

Services must be dynamic.

Do NOT hard-code individual services in Python.

An administrator can:

* Create a service.
* Edit a service.
* Enable a service.
* Disable a service.
* Delete a service if there are no dependent requests, or handle deletion safely.

A service contains:

* Name
* Active/inactive state
* Ordered fields
* Ordered statuses

Keep the service model simple.

---

# 6. Dynamic Fields

Each service defines the information that must be collected from the beneficiary.

Only three field types are required:

```text
TEXT
NUMBER
FILE
```

Each field has:

* Label/question
* Type
* Required/optional
* Display order

The administrator can add, edit, delete, and reorder fields.

The order defined by the administrator is the order shown to the beneficiary.

Do not implement complicated conditional fields.

Do not implement branching forms.

Do not implement calculated fields.

Do not implement validation rules beyond basic type/file validation.

---

# 7. File Fields

A FILE field represents exactly one uploaded file.

If multiple files are required, the administrator should create multiple FILE fields.

For example:

```text
Identity document
Bank document
Proof of address
```

should be three separate fields.

Do not implement multi-file upload fields.

Store uploaded files on the server filesystem.

Store only their metadata/path in the database.

Use a configurable maximum file size.

For the MVP, allow common document/image formats such as:

* PDF
* JPG
* JPEG
* PNG

Reject unsupported file types.

Generate safe unique filenames instead of trusting the original filename.

---

# 8. Request

A request is created when a beneficiary starts a service application.

A request contains:

* Unique request ID
* Tracking code
* Beneficiary `chat_id`
* Service
* Answers
* Current status
* Creation date

The request must preserve the answers submitted by the beneficiary.

A beneficiary may have many completed or submitted requests.

However, a beneficiary may have only ONE unfinished request at a time.

If the beneficiary already has an unfinished request, do not allow another unfinished request to be created.

---

# 9. Request Lifecycle

A request can be:

```text
UNFINISHED
SUBMITTED
or another administrator-defined status
```

The exact statuses belong to each service.

Each service has its own status list.

Administrators can:

* Create statuses.
* Rename statuses.
* Delete statuses when safe.
* Reorder statuses.

The first status can be used for newly submitted requests.

Do not build a complicated workflow engine.

A status is simply the current state of a request.

---

# 10. Status Management

Statuses are service-specific.

For example:

Loan service:

```text
Received
Under review
Approved
Rejected
Completed
```

Another service may have completely different statuses.

Do not hard-code these statuses.

The administrator should configure them through the admin panel.

When an administrator changes a request's status, save the new current status.

A simple status history is optional; do not implement it unless it is trivial.

---

# 11. Tracking Code

Every submitted request receives a unique tracking code.

The beneficiary can use the Bale bot to see their requests and their statuses.

The administrator can search for a request using its tracking code.

The tracking code should be short and human-readable.

---

# 12. Bale Bot

The Bale bot is the main beneficiary interface.

Keep the conversation simple.

The bot should provide a simple main menu.

The main functionality is:

```text
New Request
My Requests
Cancel Current Request
```

The exact button labels may be Persian.

---

# 13. Creating a Request

When the beneficiary chooses "New Request":

1. Show active services.
2. Let the beneficiary select one service.
3. Load that service's fields.
4. Ask the fields in their configured order.
5. Store each answer.
6. For FILE fields, receive one file.
7. After all required fields are completed, create/submit the request.
8. Generate a tracking code.
9. Show the tracking code to the beneficiary.

Example:

```text
Select service
      ↓
Full name
      ↓
National ID
      ↓
Bank document
      ↓
Submit
      ↓
Tracking code
```

Do not build a complicated conversation framework.

A simple state-based implementation is enough.

---

# 14. Validation

Keep validation minimal.

For TEXT:

* Accept text.

For NUMBER:

* Accept numeric input.

For FILE:

* Check file type.
* Check file size.

Do not implement complex form validation.

Do not validate whether a national ID is mathematically correct.

Do not implement external verification services.

---

# 15. Cancelling a Request

A beneficiary can cancel their unfinished request.

After cancellation:

* The request should no longer be considered the beneficiary's active unfinished request.
* Its stored data may be deleted or marked cancelled; choose the simplest safe implementation.
* The beneficiary can start a new request afterward.

A beneficiary cannot delete submitted/completed requests.

---

# 16. My Requests

The beneficiary can choose:

```text
My Requests
```

The bot should show their requests.

For each request, show only:

* Service name
* Tracking code
* Creation date
* Current status

The beneficiary can select a request to see its details.

When selected, show the submitted questions and answers.

Keep this simple.

---

# 17. Administrator Panel

The admin panel should be a simple server-rendered web interface.

Use:

* FastAPI
* Jinja2
* Plain HTML
* Minimal CSS

Do not optimize for visual beauty.

Do not build a dashboard.

Do not build charts.

Do not build animations.

The interface should simply be functional and easy to use.

Main pages:

```text
Login

Services
    ├── Service list
    ├── Create service
    └── Edit service

Requests
    ├── Request list
    └── Request details
```

---

# 18. Service Management

The administrator can:

* Create service
* Edit service
* Enable/disable service
* Delete service when safe

When editing a service, the administrator can manage:

### Fields

* Add
* Edit
* Delete
* Reorder

### Statuses

* Add
* Edit
* Delete
* Reorder

Use simple HTML forms.

Do not create a visual form builder.

---

# 19. Request Management

The administrator can see a simple list of requests.

Each row should contain:

* Tracking code
* Service
* Beneficiary name if available from answers
* Current status
* Creation date

The administrator can select a request to open its details.

---

# 20. Request Details

When an administrator opens a request, immediately show:

* Request information
* Service
* Tracking code
* Creation date
* Current status
* All questions
* All answers
* Uploaded files

The administrator can:

* Change status
* Download/view uploaded files
* Delete the request
* Send a text message to the beneficiary

Do not create complicated request editing.

Administrators do not need to edit individual answers in the MVP.

---

# 21. Searching Requests

The administrator needs to find all requests belonging to a beneficiary.

Support search by:

* Name
* National ID
* Tracking code

Name and national ID are answers stored in request fields.

The system should search submitted request answers.

The search result should include both:

* Active/current requests
* Completed/old requests

The purpose is to allow an administrator to see the complete request history of a beneficiary.

---

# 22. Filtering

Keep filtering simple.

The administrator should be able to filter requests by:

* Service
* Status

Do not implement complicated advanced filtering.

Date filtering is optional and should only be added if trivial.

---

# 23. Messaging

An administrator can send a plain text message to a beneficiary from the request details page.

The system sends the message through the Bale bot to the request's `chat_id`.

No chat history is required.

No messaging inbox is required.

No attachments are required.

Only plain text messages.

---

# 24. Deleting Requests

Administrators can permanently delete requests.

Deletion should remove:

* Request record
* Its answers
* Associated file records
* Associated uploaded files

Beneficiaries cannot permanently delete submitted requests.

Only unfinished requests can be cancelled by beneficiaries.

---

# 25. Dates

All dates displayed to administrators and beneficiaries must be Jalali/Persian dates.

Store dates internally using normal database-compatible datetime values.

Convert them to Jalali when displaying them.

Do not store Jalali dates as the primary database date format.

---

# 26. Security

Implement only practical basic security.

Required:

* Password hashing.
* Admin authentication.
* Session-based authentication.
* Protected admin routes.
* Secure file handling.
* File size limits.
* Allowed file extensions/types.
* Safe generated filenames.
* Do not expose arbitrary filesystem paths.

Do not build enterprise-level security infrastructure.

Do not implement:

* OAuth
* SSO
* RBAC
* 2FA
* Complex audit logging

unless required later.

---

# 27. Error Handling

Provide simple user-friendly error messages.

The bot should not crash because of a malformed user input.

The admin panel should show simple error messages when an operation fails.

Do not build a complex logging system.

Normal application logging is sufficient.

---

# 28. Database

Use SQLite for the MVP.

Use SQLAlchemy ORM.

Use migrations if they can be implemented simply.

Keep the schema small.

Avoid unnecessary tables and relationships.

The likely core entities are:

```text
Admin
Service
ServiceField
ServiceStatus
Request
RequestAnswer
```

Add a file-related table only if useful.

Do not create unnecessary user/profile tables.

---

# 29. Architecture

Use a simple monolithic architecture.

Everything runs as one application.

A reasonable structure is:

```text
app/
    main.py
    config.py
    database.py
    models/
    routes/
    bot/
    templates/
    static/
    services/
    utils/
```

This structure is only a guideline.

Do not create abstractions merely to follow the structure.

Prefer straightforward code.

---

# 30. Deployment

The application should be easy to run on a Linux server.

Provide:

* `.env.example`
* `requirements.txt` or equivalent
* Database initialization/migration instructions
* README
* Instructions for running the FastAPI application
* Instructions for running the Bale bot

Docker is optional.

Do not introduce Docker complexity unless it clearly simplifies deployment.

---

# 31. Explicitly Out of Scope

Do NOT implement:

* React
* Vue
* Angular
* Mobile application
* User accounts
* Beneficiary profiles
* Multiple user roles
* OAuth
* 2FA
* Payment system
* SMS
* Email
* Notifications other than Bale messages
* Complex workflow engine
* Conditional form fields
* Multi-file fields
* File versioning
* Document revision system
* Chat history
* Messaging inbox
* Analytics dashboard
* Charts
* Advanced reporting
* Export to Excel/PDF
* Complex audit logs
* AI features
* Search engine
* Microservices
* Redis
* Celery
* Kubernetes
* PostgreSQL for the MVP
* Complex frontend design

If a feature is not explicitly required by this specification, prefer NOT implementing it.

---

# 32. Development Principle

The most important rule:

## Keep Emdadyar simple.

Before adding an abstraction, library, service, database table, or feature, ask whether it is actually necessary.

Prefer:

```text
simple + working
```

over:

```text
complex + theoretically scalable
```

The application is an MVP.

It should be easy for one developer to understand and modify.

---

# 33. Implementation Order

Implement the project in these phases.

### Phase 1 — Backend Foundation

Implement:

* Project structure
* Configuration
* SQLite database
* SQLAlchemy models
* Admin authentication
* Basic application setup

Do not implement the Bale bot or full admin UI yet.

### Phase 2 — Dynamic Services and Requests

Implement:

* Services
* Dynamic fields
* Service-specific statuses
* Requests
* Answers
* Tracking codes
* Request lifecycle

Test the core request logic.

### Phase 3 — Bale Bot

Implement:

* Main menu
* Service selection
* Dynamic questions
* Text input
* Number input
* File input
* Request submission
* Tracking code
* My Requests
* Request details
* Cancel unfinished request

### Phase 4 — Admin Panel

Implement:

* Login
* Service management
* Field management
* Status management
* Request list
* Request details
* Status changes

Keep the UI plain and functional.

### Phase 5 — Search, Files and Messaging

Implement:

* Search by name
* Search by national ID
* Search by tracking code
* Service/status filters
* File viewing/downloading
* Permanent request deletion
* Sending plain text Bale messages

### Phase 6 — Finalization

Implement only what is necessary for a usable MVP:

* Fix bugs
* Basic tests
* Basic security review
* Error handling
* README
* `.env.example`
* Deployment instructions
* Remove unnecessary code

Do not add new features during this phase.

---

# 34. Agent Instructions

When implementing this specification:

1. Read this entire specification before starting a phase.
2. Implement only the requested phase.
3. Do not implement future phases early.
4. Do not add features that are out of scope.
5. Do not over-engineer.
6. Keep dependencies minimal.
7. Reuse existing code instead of creating duplicate abstractions.
8. Run relevant tests after implementation.
9. Fix errors before declaring the phase complete.
10. Do not modify unrelated files.
11. Keep the UI extremely simple.
12. Prioritize working functionality over visual quality.
13. If a design decision is not specified, choose the simplest reasonable solution.
14. Do not ask for permission for routine implementation decisions.
15. If a requirement is genuinely ambiguous and affects the architecture, stop and ask for clarification.

The goal is not to build a large production platform.

The goal is to build a small, reliable, maintainable MVP that satisfies the requirements above.
