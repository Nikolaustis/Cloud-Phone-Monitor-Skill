# packaging validation

Validation performed before packaging:

- Python regression suite: **49 passed, 13 subtests passed**.
- Includes fixes for the previously pre-existing missing external UgPhone patcher test and VSPhone replay fixture initialization.
- gzip Dashboard validator test passes with partial collection coverage treated as a warning rather than a publication blocker.
- Source-package cleanliness validator passes after packaging exclusions.
- No `output/`, `baselines/`, auth state, cookies/tokens, `node_modules/`, `dist/`, generated Dashboard data, `__pycache__/`, or `*.pyc` are included.
- PowerShell scripts were reviewed structurally for Windows PowerShell 5.1 compatibility; this Linux packaging environment does not provide a PowerShell runtime, so the Windows scripts could not be executed here.
