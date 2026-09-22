# SQLite history

Install the `persistence` extra. The composition root initializes a configurable SQLite
file, defaulting to `data/psd_analyzer.db`; the Streamlit entry point accepts the
`PSD_ANALYZER_DB` environment variable. Tests always use temporary files.

```python
from psd_analyzer.infrastructure.persistence import create_repository
from psd_analyzer.application.dto.history import AnalysisType, HistoryFilter
from psd_analyzer.application.use_cases.history import SaveAnalysis, ListAnalysisHistory
from uuid import uuid4

repository = create_repository("data/psd_analyzer.db")
# result is an existing Application AnalysisResult.
saved = SaveAnalysis(repository).execute(
    result, AnalysisType.PRODUCTION_MONITORING, analysis_id=str(uuid4())
)
summaries = ListAnalysisHistory(repository).execute(HistoryFilter(recipe_id="R001"))
```

`init_db(path)` centrally calls SQLAlchemy `metadata.create_all`; no migrations or
external server are required for this first schema. It returns an Engine for explicit
composition or tests. File databases use short-lived connections and `NullPool`.
Domain and Application never import SQLAlchemy. Application depends only on the
`AnalysisRepository` Protocol.

## Saved data and transaction boundaries

`analyses` stores typed query columns: UTC timestamp, analysis type, recipe identity
and version, equivalent/target q, particle bounds, interpolation/model and error
metrics. A convention fingerprint identifies profile, algorithm, calculation grid,
recipe fractions and measurement protocol; trend plots can avoid connecting
incompatible numerical conventions.

`analysis_snapshots` holds current and, for substitutions, original snapshots.
`analysis_materials` preserves batches, supplier/density metadata, measurement identity,
source hash, fractions and actual weights. `analysis_psd_points` contains measured,
mixed, fitted, target and signed comparison curves. `analysis_key_sizes`,
`analysis_metrics`, `analysis_recipe_lines` and `analysis_diagnostics` preserve the
remaining result data. Small profile/fit configuration and variable identity metadata
use JSON. PSD vectors are relational rows. No pickle, Plotly figures or HTML are saved.

A save transaction writes every table or rolls back all changes. A UUID is assigned to
the analysis before saving and retained by the UI. Repeating the UUID with identical
result/type returns the original record, including its original timestamp. Changed
content under the same UUID raises `AnalysisConflict`; it never overwrites a snapshot.
Analysis is not automatically saved. The user explicitly selects **Save Analysis**.

`StoredAnalysis.result` reconstructs the existing immutable `AnalysisResult` or
`ComparisonResult` exactly, including both substitution snapshots. `current` accesses
the primary analysis. All saved timestamps are timezone-aware and normalized to UTC;
naive timestamps are rejected. SQL failures become `RepositoryError`.

## Query, comparison and baseline

`ListAnalysisHistory` returns lightweight `AnalysisSummary` objects using SQL filters
for recipe ID/version, inclusive UTC date range, type and batch number. It does not
select PSD points. The default limit is 1,000 (maximum 10,000), newest first. Detail
loading happens through `GetAnalysisDetail` only when requested.

Types are `PRODUCTION_MONITORING`, `MATERIAL_SUBSTITUTION` and `RECIPE_SIMULATION`.
Simulation records require a draft recipe and explicit simulation flag. Production
and substitution records require the released recipe snapshot.

`SetBaselineAnalysis` is an explicit operation. A primary-key association guarantees
at most one production baseline per recipe ID + version; setting a new one atomically
replaces that association. Simulation and substitution records cannot become the
production baseline. `GetBaselineAnalysis` returns `None` until one is selected.

`CompareHistoricalAnalyses` loads two snapshots and delegates to the existing domain
comparison service. Type and recipe/version must match, followed by the existing
profile, algorithm, protocol, fractions and grid checks. Incompatible history is
reported rather than silently resampled or refitted. Existing historical results are
never changed during comparison.

History records document analyses and reference deviations. They are not formal
product quality determinations or a production recipe approval database.
