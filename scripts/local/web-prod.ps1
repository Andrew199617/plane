# Retired by the release/debug split: the production web build is now served by the RELEASE stack
# (container plane-release-proxy on 127.0.0.1:3300), deployed only with scripts/local/release.ps1.
# See AGENTS.md "Local environment (Jira-parity fork)".
Write-Error 'retired: see AGENTS.md (scripts/local/release.ps1)'
exit 1
