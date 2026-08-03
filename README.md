# Campaign Analytics Platform

The foundation for a reusable Streamlit analytics platform for vaccination campaigns.

## Run locally

Use Python 3.12 or newer, then install the project dependencies and start Streamlit:

```powershell
python -m pip install -e .
streamlit run app.py
```

Analysis modules are intentionally not included yet. The current application provides
the platform shell, dynamic module registry, themed layout, and upload workspace.

## Adding a module later

Create a folder under `src/campaign_analytics/modules/` and add a `module.toml`
manifest. The registry will discover it and add it to the sidebar automatically.
The module can remain unavailable until it supplies its entry point.

```toml
id = "vaccination_analysis"
name = "Vaccination Analysis"
group = "Campaign Modules"
icon = "💉"
order = 10
status = "planned" # planned, beta, or active
entry_point = "campaign_analytics.modules.vaccination_analysis.view:render"
```

Only manifests with `status = "active"` and a valid entry point can be opened.
Planned modules remain visible as “Soon”, allowing the navigation structure to grow
without introducing analysis code prematurely.
