# Campaign Analytics Platform — Project Context

## Purpose

Campaign Analytics Platform is an offline-capable Streamlit application for analysing
vaccination-campaign operations. It is designed as a reusable platform, rather than a
single dashboard, for Polio, OCV, Measles, and future campaign datasets.

Every analysis module owns its complete workflow: upload, column mapping, validation,
processing, summary statistics, visualisations, tables, and result downloads.

## Folder structure

```text
.
├── app.py                              # Streamlit entry point
├── .streamlit/config.toml              # Streamlit theme and server defaults
├── config/                             # Reserved for environment-safe configuration
├── data/                               # Local-development upload, processing, export folders
├── logs/                               # Rotating application logs (not versioned)
├── src/campaign_analytics/
│   ├── components/                     # Reusable UI: charts, upload, mapper, tables, KPI, layout
│   ├── core/                           # Session, registry, navigation, errors, logging, storage
│   ├── modules/                        # Independently discoverable campaign modules
│   │   ├── vaccination/
│   │   └── teams_reporting/
│   └── ui/                             # Application shell and compatibility UI imports
├── tests/modules/                      # Pure module processing tests
├── pyproject.toml                      # Package metadata and tool configuration
└── requirements.txt                    # Runtime dependency installation list
```

## Coding conventions

- Python 3.12+; type hints and docstrings for public functions.
- PEP 8 formatting, 88-character target line length, and modular functions.
- Keep Streamlit UI separate from pure data processing and validation.
- Modules must not import or depend on another module's implementation.
- Use shared components from `campaign_analytics.components` for common UI patterns.
- Prefer Pandas for tabular processing, Plotly for interactive charts, and Openpyxl for
  Excel exports.
- Never hard-code secrets or production paths. Uploaded campaign data is treated as
  sensitive and is not committed to source control.

## Completed phases

### Phase 1 — Platform foundation

- Streamlit application entry point, dependency definitions, theme configuration, and
  local data/log directory structure.
- Manifest-driven module registry and session-state defaults.
- Temporary file-staging workspace.

### Phase 2 — Initial independent analysis modules

- Vaccination Analysis: separately mapped Target Population and eTally inputs;
  independent nOPV and bOPV LGA coverage calculations, validation, charts, tables,
  and separate CSV/Excel downloads.
- Teams Reporting: separately mapped eTally and Team Distribution inputs; user-defined
  two- or three-column Team IDs, distinct-team counts, LGA reporting calculations,
  validation, charts, tables, and CSV/Excel downloads.

### Phase 3 — Main application experience

- Responsive modern landing page, sidebar navigation, module discovery, theme, shared
  layout, reusable component library, logging, and user-safe error handling.

## Remaining phases

- Define and implement a published module-summary contract for the campaign dashboard.
- Add Supervisor Checklist, MST Checklist, AFP Cases, Child Absent, Settlement
  Visitation, Vaccine Utilization, GIS Coverage, and Zero Dose modules as requested.
- Add campaign/run management, persistent production storage, and configurable data
  retention.
- Add authentication, roles, audit logging, deployment configuration, and automated
  end-to-end tests before production use.
- Consolidate module-internal UI controls onto shared components during planned module
  enhancement work; do not change validated module logic solely for refactoring.

## Key design decisions

- **Modular monolith:** one Streamlit deployment with independently discoverable
  module packages. A `module.toml` manifest makes a module appear in the sidebar.
- **No cross-module calculation coupling:** modules process their own data. The future
  dashboard will read published summaries, not call module processors directly.
- **Offline-first operation:** core workflows rely only on local files and installed
  Python packages; no network calls are required at runtime.
- **Session state for UI only:** active page, uploads, and in-progress selection state
  live in Streamlit session state. Large or persistent datasets belong in storage.
- **Confirmed mappings:** the Vaccination module validates only after users click
  `Apply column mappings`; unconfirmed selector changes never refresh or replace
  prior validation/results.
- **User-safe errors:** unexpected rendering errors receive a support reference and are
  written to rotating logs; stack traces are not shown to users.
