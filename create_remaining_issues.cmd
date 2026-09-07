@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Environmental Assurance - create remaining GitHub issues
REM Assumes issues 1-5 already exist.
REM Run this from the Git repository root.
REM Requires GitHub CLI: gh
REM ============================================================

where gh >nul 2>&1
if errorlevel 1 (
    echo ERROR: GitHub CLI "gh" is not installed or not on PATH.
    exit /b 1
)

gh auth status >nul 2>&1
if errorlevel 1 (
    echo ERROR: GitHub CLI is not authenticated.
    echo Run: gh auth login
    exit /b 1
)

for /f "delims=" %%R in ('gh repo view --json nameWithOwner -q ".nameWithOwner"') do (
    set "REPO=%%R"
)

if not defined REPO (
    echo ERROR: Could not determine GitHub repository.
    echo Make sure you are running this inside the repository.
    exit /b 1
)

echo.
echo ============================================================
echo Repository: !REPO!
echo ============================================================
echo.

REM ------------------------------------------------------------
REM Priority labels
REM ------------------------------------------------------------

echo Ensuring priority labels exist...

gh label create P0 --color B60205 --description "Must ship for core MVP" --force >nul 2>&1
gh label create P1 --color D93F0B --description "High priority MVP work" --force >nul 2>&1
gh label create P2 --color FBCA04 --description "Important if time permits" --force >nul 2>&1
gh label create P3 --color 0E8A16 --description "Post-MVP or optional integration" --force >nul 2>&1

REM ------------------------------------------------------------
REM New milestones that do not fit your existing milestone set
REM ------------------------------------------------------------

call :ensure_milestone "Investigation Intelligence"
call :ensure_milestone "Data Ingestion & Reliability"
call :ensure_milestone "Post-MVP Integrations"

REM Temporary issue body file
set "BODY=%TEMP%\env_assurance_issue_body.md"

REM ============================================================
REM ISSUE 6
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Make peat a first-class environmental attribute of every FireEvent.
echo.
echo ## Tasks
echo - [ ] Cache the peat dataset locally or in the backend store.
echo - [ ] Implement point and radius lookup.
echo - [ ] Calculate peat_fraction for an event buffer.
echo - [ ] Calculate distance_to_peat.
echo - [ ] Identify direct peat intersection.
echo - [ ] Calculate peat fraction along a corridor between linked events.
echo - [ ] Return source resolution and limitations.
echo - [ ] Do not infer underground combustion from peat overlap alone.
echo.
echo ## Acceptance criteria
echo A FireEvent can return structured peat intersection, peat fraction, distance and provenance evidence.
)

call :create_issue ^
"[06] Add peat intersection and context service" ^
"Modeling Environment History" ^
"P0"

REM ============================================================
REM ISSUE 7
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Quantify the workload reduction produced by the prototype using a reproducible manual-versus-automated benchmark.
echo.
echo ## Manual benchmark
echo - [ ] Retrieve FIRMS history manually.
echo - [ ] Reconstruct event chronology.
echo - [ ] Retrieve historical weather.
echo - [ ] Inspect peat context.
echo - [ ] Identify neighbouring events.
echo - [ ] Find suitable imagery metadata.
echo - [ ] Assemble an evidence summary.
echo - [ ] Record total analyst time.
echo.
echo ## Automated benchmark
echo - [ ] Run the same case through the product.
echo - [ ] Measure evidence assembly time.
echo - [ ] Measure observations-to-events compression.
echo - [ ] Measure events-to-human-review compression.
echo - [ ] Measure evidence-field completeness.
echo - [ ] Record number of manual interactions.
echo.
echo ## Acceptance criteria
echo Produce a defensible prototype benchmark comparing manual environmental evidence reconstruction against the automated workflow.
echo Do not claim that the entire audit process is reduced by the same amount.
)

call :create_issue ^
"[07] Create auditor workload reduction benchmark" ^
"Demo Ready" ^
"P0"

REM ============================================================
REM ISSUE 8
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Create stable historical demo cases and regression fixtures.
echo.
echo ## Tasks
echo - [ ] Select 3 to 5 historical 2019 Sumatra or Kalimantan cases.
echo - [ ] Freeze relevant FIRMS observations.
echo - [ ] Freeze weather responses.
echo - [ ] Freeze peat context.
echo - [ ] Freeze imagery metadata.
echo - [ ] Define expected clustering outcomes.
echo - [ ] Define expected evidence fields.
echo - [ ] Include one simple event.
echo - [ ] Include one complex multi-lobe event.
echo - [ ] Include one peat-related event.
echo.
echo ## Acceptance criteria
echo The same historical fixtures produce stable event and evidence outputs across development changes.
)

call :create_issue ^
"[08] Build golden historical regression cases" ^
"Demo Ready" ^
"P0"

REM ============================================================
REM ISSUE 9
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Implement cheap deterministic triage before expensive evidence acquisition or AI analysis.
echo.
echo ## Features
echo - [ ] FIRMS confidence.
echo - [ ] FRP.
echo - [ ] Repeat observations.
echo - [ ] Vegetated land context.
echo - [ ] Urban context.
echo - [ ] Settlement context.
echo - [ ] Persistent heat-source indicator.
echo - [ ] Volcano or geothermal context.
echo - [ ] Recent rainfall.
echo - [ ] Nearby detections.
echo.
echo ## Output states
echo - [ ] LIKELY_FIRE
echo - [ ] LIKELY_NON_FIRE
echo - [ ] AMBIGUOUS
echo.
echo ## Acceptance criteria
echo Deterministic rules handle obvious cases and record which evidence caused each decision.
echo Only ambiguous cases should require AI review.
)

call :create_issue ^
"[09] Implement deterministic Stage 1 triage" ^
"Stage 1 Cluster Fire Event Triage" ^
"P1"

REM ============================================================
REM ISSUE 10
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Represent possible relationships between coherent FireEvents as a graph.
echo.
echo ## Edge features
echo - [ ] Geographic distance.
echo - [ ] Elapsed time.
echo - [ ] Wind alignment.
echo - [ ] Directional compatibility.
echo - [ ] Overlapping event buffers.
echo - [ ] Peat corridor fraction.
echo - [ ] Shared environmental episode.
echo - [ ] Historical recurrence.
echo - [ ] Propagation compatibility.
echo.
echo ## Edge states
echo - [ ] RELATED_POSSIBLE
echo - [ ] PROPAGATION_COMPATIBLE
echo - [ ] PROPAGATION_WEAK
echo - [ ] INDEPENDENT_PLAUSIBLE
echo - [ ] UNRESOLVED
echo.
echo ## Acceptance criteria
echo Event relationships are represented deterministically before an LLM receives the evidence.
)

call :create_issue ^
"[10] Build FireEventGraph relationship model" ^
"Fire Event Cluster Correlation" ^
"P1"

REM ============================================================
REM ISSUE 11
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Add a first-order surface-fire propagation model for transparency and plausibility testing.
echo.
echo ## Tasks
echo - [ ] Implement a wind-oriented elliptical spread model.
echo - [ ] Support head, back and flank spread parameters.
echo - [ ] Update orientation using historical wind.
echo - [ ] Compare subsequent hotspot clusters against the expected envelope.
echo - [ ] Calculate a propagation compatibility indicator.
echo - [ ] Record observations outside the projected envelope.
echo - [ ] Label the model as a first-order estimate.
echo - [ ] Keep underground peat spread out of this model.
echo.
echo ## Acceptance criteria
echo The UI can visually compare observed event progression against a simple expected surface-fire envelope.
)

call :create_issue ^
"[11] Add surface fire-growth compatibility model" ^
"Fire Growth Transparency" ^
"P1"

REM ============================================================
REM ISSUE 12
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Create explainable Fire Complexity evidence from reconstructed events.
echo.
echo ## Features
echo - [ ] Duration.
echo - [ ] Observation count.
echo - [ ] Spatial extent.
echo - [ ] Centroid movement.
echo - [ ] Directional consistency.
echo - [ ] Wind alignment.
echo - [ ] FRP variability.
echo - [ ] Distinct thermal lobes.
echo - [ ] Peat overlap.
echo - [ ] Nearby event count.
echo - [ ] Historical recurrence.
echo - [ ] Unexplained detections.
echo - [ ] Surface propagation mismatch.
echo.
echo ## Acceptance criteria
echo Fire complexity is explained through individual evidence fields rather than a hidden magic score.
)

call :create_issue ^
"[12] Add explainable Fire Complexity evidence" ^
"Stage 1 Cluster Fire Event Triage" ^
"P1"

REM ============================================================
REM ISSUE 13
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Select useful Sentinel scenes before downloading large imagery products.
echo.
echo ## Sentinel-2
echo - [ ] Select closest usable pre-event scene.
echo - [ ] Select closest usable post-event scene.
echo - [ ] Apply cloud-cover threshold.
echo - [ ] Calculate temporal distance from event.
echo.
echo ## Sentinel-1
echo - [ ] Select suitable pre-event scene.
echo - [ ] Select suitable post-event scene.
echo - [ ] Store orbit metadata.
echo - [ ] Store product ID.
echo.
echo ## Acceptance criteria
echo Every selected scene stores acquisition time, sensor, product ID, quality metadata and temporal distance.
)

call :create_issue ^
"[13] Build Copernicus scene selector" ^
"Modeling Environment History" ^
"P1"

REM ============================================================
REM ISSUE 14
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Rank human investigative attention without scoring guilt or company responsibility.
echo.
echo ## Candidate factors
echo - [ ] Event validity.
echo - [ ] Environmental significance.
echo - [ ] Event complexity.
echo - [ ] Evidence inconsistency.
echo - [ ] Unresolved event relationships.
echo - [ ] Evidence sufficiency.
echo - [ ] Peat involvement.
echo - [ ] Land-change indicators.
echo - [ ] Propagation uncertainty.
echo.
echo ## Exclusions
echo - [ ] Do not use company reputation.
echo - [ ] Do not use previous misconduct.
echo - [ ] Do not use company identity.
echo.
echo ## Output
echo LOW, MEDIUM, HIGH or URGENT investigation priority with transparent supporting evidence.
)

call :create_issue ^
"[14] Implement Investigation Priority scoring" ^
"Investigation Intelligence" ^
"P1"

REM ============================================================
REM ISSUE 15
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Run evidence-linked Investigator and Skeptic analysis only after deterministic reconstruction.
echo.
echo ## Tasks
echo - [ ] Agents receive structured evidence IDs only.
echo - [ ] Round 1 independent assessment.
echo - [ ] Round 2 rebuttal.
echo - [ ] Round 3 final structured assessment.
echo - [ ] Maximum three rounds.
echo - [ ] Preserve unresolved disagreement.
echo - [ ] Do not expose raw chain-of-thought.
echo - [ ] Require evidence IDs for factual claims.
echo.
echo ## Roles
echo Investigator asks what evidence justifies further human verification.
echo Skeptic asks what alternative explanation or evidence limitation could explain the same observations.
)

call :create_issue ^
"[15] Implement Investigator and Skeptic structured analysis" ^
"Investigation Intelligence" ^
"P1"

REM ============================================================
REM ISSUE 16
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Convert unresolved evidence into concrete human verification tasks.
echo.
echo ## Example verification actions
echo - [ ] Inspect an intervening peat corridor.
echo - [ ] Compare incident logs for linked events.
echo - [ ] Verify an event's apparent origin.
echo - [ ] Request higher-resolution imagery.
echo - [ ] Inspect historical fire-response records.
echo - [ ] Verify local water or drainage conditions.
echo - [ ] Request relevant worker or community evidence.
echo.
echo ## Acceptance criteria
echo Every high-priority unresolved event contains one to three evidence-linked recommended verification actions.
)

call :create_issue ^
"[16] Generate targeted field-verification questions" ^
"Investigation Intelligence" ^
"P1"

REM ============================================================
REM ISSUE 17
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Make Map and Table views operate on one shared FireEvent state.
echo.
echo ## Tasks
echo - [ ] Selecting a map event selects the matching table row.
echo - [ ] Selecting a table row selects and pans to the map event.
echo - [ ] Preserve selection when switching views.
echo - [ ] Sort by investigation priority.
echo - [ ] Filter by event status.
echo - [ ] Filter by peat classification.
echo - [ ] Toggle raw FIRMS observations.
echo - [ ] Toggle FireEvent markers.
echo - [ ] Toggle FireEventGraph links.
)

call :create_issue ^
"[17] Wire Map and Table to shared FireEvent state" ^
"Auditor Interface" ^
"P1"

REM ============================================================
REM ISSUE 18
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Clean the Indonesia regional map so neighbouring Malaysian detections do not appear as unexplained ocean noise.
echo.
echo ## Tasks
echo - [ ] Keep authoritative Indonesia geography.
echo - [ ] Add lightweight Malaysia context or equivalent regional basemap.
echo - [ ] Separate Indonesian events from external context detections.
echo - [ ] Hide distant external detections by default.
echo - [ ] Preserve nearby Malaysian detections when potentially relevant.
echo - [ ] Never delete external raw observations from storage.
echo.
echo ## Acceptance criteria
echo The default demo map clearly communicates the Indonesia analysis scope while preserving relevant cross-border context.
)

call :create_issue ^
"[18] Clean Indonesia and Malaysia geodata rendering" ^
"FIRMS Geodata Validation" ^
"P1"

REM ============================================================
REM ISSUE 19
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Implement historical event replay for auditors.
echo.
echo ## Tasks
echo - [ ] FIRMS observations appear over time.
echo - [ ] FireEvent state evolves over time.
echo - [ ] Weather values update.
echo - [ ] Wind direction updates.
echo - [ ] Event links become visible as evidence appears.
echo - [ ] Sensor layers show NO PASS when no observation exists.
echo - [ ] Add play and pause controls.
echo - [ ] Support short and extended lookback modes.
)

call :create_issue ^
"[19] Implement historical timeline replay" ^
"Auditor Interface" ^
"P1"

REM ============================================================
REM ISSUE 20
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Build the auditor-facing investigation report screen.
echo.
echo ## Sections
echo - [ ] Executive summary.
echo - [ ] Event chronology.
echo - [ ] Direct observations.
echo - [ ] Weather reconstruction.
echo - [ ] Peat context.
echo - [ ] Surface propagation compatibility.
echo - [ ] Event graph.
echo - [ ] Top hypotheses.
echo - [ ] Investigator and Skeptic disagreement.
echo - [ ] Recommended verification.
echo - [ ] Limitations.
echo - [ ] Provenance.
echo - [ ] Human auditor notes.
echo.
echo ## Acceptance criteria
echo The report separates observed evidence, deterministic metrics, AI interpretation and human decision support.
)

call :create_issue ^
"[20] Build investigation report view" ^
"Auditor Interface" ^
"P1"

REM ============================================================
REM ISSUE 21
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Add Sentinel-2 before and after environmental-change evidence.
echo.
echo ## Tasks
echo - [ ] Build pre-event composite.
echo - [ ] Build post-event composite.
echo - [ ] Calculate NDVI where appropriate.
echo - [ ] Calculate NDMI.
echo - [ ] Calculate dNBR where feasible.
echo - [ ] Render burn-scar or vegetation-change visualization.
echo - [ ] Preserve imagery provenance.
echo - [ ] Store cloud-quality flag.
)

call :create_issue ^
"[21] Add Sentinel-2 pre and post processing" ^
"Modeling Environment History" ^
"P2"

REM ============================================================
REM ISSUE 22
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Add Sentinel-1 change evidence for cloud-independent environmental reconstruction.
echo.
echo ## Tasks
echo - [ ] Retrieve suitable pre-event backscatter.
echo - [ ] Retrieve suitable post-event backscatter.
echo - [ ] Prefer analysis-ready products where available.
echo - [ ] Calculate a simple change metric.
echo - [ ] Preserve acquisition and orbit metadata.
echo - [ ] Add explicit evidence limitations.
echo.
echo ## Required limitation
echo SAR change is non-specific and does not independently establish burning, clearing or underground fire movement.
)

call :create_issue ^
"[22] Add Sentinel-1 change evidence" ^
"Modeling Environment History" ^
"P2"

REM ============================================================
REM ISSUE 23
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Optionally refine the simple surface-fire model using a single Kalman filter.
echo.
echo ## State
echo - [ ] Centroid.
echo - [ ] Major axis.
echo - [ ] Minor axis.
echo - [ ] Orientation.
echo - [ ] Spread rate.
echo.
echo ## Tasks
echo - [ ] Assimilate clustered hotspot measurements.
echo - [ ] Update ellipse estimates.
echo - [ ] Visualize predicted versus observed extent.
echo - [ ] Label output as approximate.
echo.
echo ## Constraint
echo Do not allow this issue to block the hackathon MVP.
)

call :create_issue ^
"[23] Add optional Kalman fire-growth refinement" ^
"Fire Growth Transparency" ^
"P2"

REM ============================================================
REM ISSUE 24
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Export an Environmental Fire Investigation Pack for auditor handoff and demo.
echo.
echo ## Tasks
echo - [ ] Generate from structured evidence only.
echo - [ ] Include evidence IDs.
echo - [ ] Include provenance.
echo - [ ] Include uncertainty and limitations.
echo - [ ] Include event map.
echo - [ ] Include environmental timeline.
echo - [ ] Include field-verification questions.
echo - [ ] Export PDF.
echo.
echo ## Mandatory disclaimer
echo This report is an investigative-support product. It does not establish legal responsibility, intent, ownership liability, culpability or criminal wrongdoing. Findings require human verification.
)

call :create_issue ^
"[24] Generate Environmental Fire Investigation Pack PDF" ^
"Demo Ready" ^
"P2"

REM ============================================================
REM ISSUE 25
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Add Global Forest Watch concession attribute lookup as a post-MVP integration.
echo.
echo ## Tasks
echo - [ ] Implement point-in-polygon lookup.
echo - [ ] Return concession attributes only.
echo - [ ] Do not persist raw concession geometry.
echo - [ ] Keep concession identity outside physical-causation scoring.
echo - [ ] Preserve source provenance.
echo - [ ] Skip cleanly when the API key is unavailable.
)

call :create_issue ^
"[25] Add Global Forest Watch concession lookup" ^
"Post-MVP Integrations" ^
"P3"

REM ============================================================
REM ISSUE 26
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Evaluate and integrate BMKG as a corroborating Indonesian weather source.
echo.
echo ## Tasks
echo - [ ] Document available public feeds.
echo - [ ] Determine what authenticated access unlocks.
echo - [ ] Identify useful historical products.
echo - [ ] Compare against Open-Meteo and NASA POWER.
echo - [ ] Preserve disagreement between sources.
echo.
echo ## Constraint
echo BMKG is useful validation but must not block the MVP.
)

call :create_issue ^
"[26] Add BMKG corroborating weather integration" ^
"Post-MVP Integrations" ^
"P3"

REM ============================================================
REM ISSUE 27
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Port source polling and refresh logic into the production ingestion worker.
echo.
echo ## Cadence
echo - [ ] FIRMS roughly daily.
echo - [ ] Open-Meteo and POWER hourly or daily.
echo - [ ] Sentinel-1 according to available passes.
echo - [ ] Sentinel-2 when suitable low-cloud imagery exists.
echo - [ ] WorldCover static refresh only on new epoch.
echo - [ ] Peat dataset static refresh only when upstream changes.
echo - [ ] OSM periodic refresh.
echo.
echo ## Reliability
echo - [ ] Record last_success_at.
echo - [ ] Record upstream failures.
echo - [ ] Prevent duplicate ingestion.
echo - [ ] Keep historical backfill separate from live polling.
)

call :create_issue ^
"[27] Port source polling to ingestion worker" ^
"Data Ingestion & Reliability" ^
"P2"

REM ============================================================
REM ISSUE 28
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Turn discovered HTTP integration failures into permanent regression protection.
echo.
echo ## Tasks
echo - [ ] Keep Windows OS trust-store support.
echo - [ ] Set an explicit User-Agent.
echo - [ ] Add HTTP timeout policy.
echo - [ ] Add bounded retry policy.
echo - [ ] Handle rate limits.
echo - [ ] Log source URL and status.
echo - [ ] Add FIRMS TLS regression test.
echo - [ ] Add Overpass 406 regression test.
echo - [ ] Detect HTTP 200 empty historical Overpass responses.
)

call :create_issue ^
"[28] Harden shared HTTP client and source reliability" ^
"Data Ingestion & Reliability" ^
"P1"

REM ============================================================
REM ISSUE 29
REM ============================================================

> "%BODY%" (
echo ## Goal
echo Encode known source and model limitations directly in code and documentation.
echo.
echo ## Required limitations
echo - [ ] FIRMS Area API historical windows are capped at five days per request.
echo - [ ] FIRMS observations are not equivalent to individual fires.
echo - [ ] Open-Meteo is point-specific.
echo - [ ] NASA POWER is point-specific.
echo - [ ] WorldCover only provides the available static epochs.
echo - [ ] Do not treat WorldCover 2020 as contemporaneous 2019 land cover.
echo - [ ] Global peat data is static.
echo - [ ] Current Overpass instance does not provide trustworthy historical attic queries.
echo - [ ] Copernicus catalogue search does not require product-download authentication.
echo - [ ] SAR change is non-specific.
echo - [ ] Elliptical fire growth is only an approximate surface-propagation model.
)

call :create_issue ^
"[29] Document and enforce source limitations" ^
"Data Ingestion & Reliability" ^
"P1"

del "%BODY%" >nul 2>&1

echo.
echo ============================================================
echo Finished creating remaining issues.
echo ============================================================
echo.
echo Milestone mapping used:
echo.
echo   FIRMS Geodata Validation
echo     - 18
echo.
echo   Fire Events Modelling
echo     - First five issues already created
echo.
echo   Modeling Environment History
echo     - 06, 13, 21, 22
echo.
echo   Stage 1 Cluster Fire Event Triage
echo     - 09, 12
echo.
echo   Fire Event Cluster Correlation
echo     - 10
echo.
echo   Fire Growth Transparency
echo     - 11, 23
echo.
echo   Investigation Intelligence [NEW]
echo     - 14, 15, 16
echo.
echo   Auditor Interface
echo     - 17, 19, 20
echo.
echo   Demo Ready
echo     - 07, 08, 24
echo.
echo   Data Ingestion ^& Reliability [NEW]
echo     - 27, 28, 29
echo.
echo   Post-MVP Integrations [NEW]
echo     - 25, 26
echo.
echo Done.
exit /b 0


REM ============================================================
REM Helpers
REM ============================================================

:ensure_milestone
set "MS=%~1"
set "MS_FOUND="

for /f "delims=" %%M in ('gh api "repos/!REPO!/milestones?state=all^&per_page=100" --jq ".[] ^| select(.title == \"!MS!\") ^| .number" 2^>nul') do (
    set "MS_FOUND=%%M"
)

if defined MS_FOUND (
    echo Milestone exists: !MS!
) else (
    echo Creating milestone: !MS!
    gh api --method POST "repos/!REPO!/milestones" -f title="!MS!" >nul
)

exit /b 0


:create_issue
set "TITLE=%~1"
set "MILESTONE=%~2"
set "PRIORITY=%~3"
set "ISSUE_FOUND="

REM Skip an issue if an issue with the exact title already exists.
for /f "delims=" %%I in ('gh issue list --state all --limit 500 --json title --jq ".[] ^| select(.title == \"!TITLE!\") ^| .title" 2^>nul') do (
    set "ISSUE_FOUND=%%I"
)

if defined ISSUE_FOUND (
    echo [SKIP] !TITLE!
    exit /b 0
)

echo [CREATE] !TITLE!
echo          milestone: !MILESTONE!
echo          priority:  !PRIORITY!

gh issue create ^
    --title "!TITLE!" ^
    --body-file "!BODY!" ^
    --milestone "!MILESTONE!" ^
    --label "!PRIORITY!"

if errorlevel 1 (
    echo ERROR creating: !TITLE!
) else (
    echo.
)

exit /b 0