# S3WaaS Anomaly List: Broken /en Redirects

The following districts exhibit non-standard behavior where `url/en` redirects to a specific notice or page instead of the English homepage. However, many still have accessible `/documents/` endpoints.

## Detected Anomalies
1. **South Andaman District (`southandaman.nic.in`)**
   - Redirects `/en` -> `/notice/environmental-clearance-for-mining...`
   - **Fix**: Direct access to `/documents/` works (200 OK).

2. **Ananthapuramu District (`ananthapuramu.ap.gov.in`)**
   - Redirects `/en` -> `/notice/engaging-senior-residents...`
   - **Fix**: Direct access to `/documents/` works (200 OK).

3. **Srikakulam District (`srikakulam.ap.gov.in`)**
   - Redirects `/en` -> `/notice/engineering-assistant-grade-ii...`
   - **Fix**: Direct access to `/documents/` works (200 OK).

4. **Lower Dibang Valley (`roing.nic.in`)**
   - Redirects `/en` -> `/notice/enforcement-of-mcc/`
   - **Fix**: Direct access to `/documents/` works (200 OK).

5. **Bokaro District (`bokaro.nic.in`)** (User Reported)
   - Redirects `/en` -> Specific notice.
   - **Fix**: Use `/documents/` or specific category links.

## Recommendation
This list validates the "Bokaro Behavior" is a widespread pattern (likely a CMS config error on their end).
**Strategy**: If `url/en` redirects to a `.../notice/...` path, the S3WaaS Adapter should flag it as "Broken Home" and fallback to scraping `/documents/` directly.
