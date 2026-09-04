# Authentication Design

## Two-stage login protocol

Agent-driven login uses a session-bound two-stage protocol:

```text
LOGIN.ps1 <Platform> -Start
  -> controller creates UUID session
  -> local headed Playwright browser opens
  -> WAITING_FOR_USER

user completes login locally

LOGIN.ps1 <Platform> -Complete
  -> same session UUID is signaled
  -> helper verifies authenticated business state
  -> pending auth artifacts are re-opened/verified
  -> verified artifacts are committed
  -> SAVED_AND_VERIFIED
```

Historical status files cannot satisfy a new session. Signal, status, controller metadata, and pending filenames are bound to the current UUID.

## UgPhone

UgPhone retains three local authentication layers:

```text
output/auth/ugphone_profile/
output/auth/ugphone_state.json
output/auth/ugphone_runtime_context.json
```

The helper verifies purchase-page business data and required pricing API evidence, then reopens the persistent profile in headed and scheduled-task-equivalent headless modes. File artifacts are committed only after verification. The persistent Chromium profile itself cannot participate in the same multi-file atomic transaction and is documented accordingly.

## Other platforms

VSPhone, Redfinger, and LDCloud require both server-acknowledged authentication evidence and business/price-page evidence after re-opening the saved state. Generic token/cookie presence is diagnostic only.

## Persistent-profile lock

UgPhone login and collection must not open the same persistent profile concurrently. `profile_lock.py` creates an atomic lock next to the profile using exclusive file creation. Lock ownership contains process identity and an opaque lease ID. Only a definitely dead owner is automatically cleaned; uncertain live ownership fails closed.
