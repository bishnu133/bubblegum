#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/run_webview_readiness_real_trials.sh <android|ios|cloud|all> [--dry-run]

Description:
  Runs existing real-env WebView readiness smoke pytest commands for the selected platform(s).

Options:
  --dry-run   Print required environment checks and pytest commands without executing tests.

Notes:
  - Script does not set secret variables.
  - Script does not print secret values.
  - Script validates required environment variables before non-dry-run execution.
USAGE
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 2
fi

platform="$1"
dry_run="0"

if [[ $# -eq 2 ]]; then
  if [[ "$2" != "--dry-run" ]]; then
    usage
    exit 2
  fi
  dry_run="1"
fi

case "$platform" in
  android|ios|cloud|all) ;;
  *)
    usage
    exit 2
    ;;
esac

redacted_status() {
  local var_name="$1"
  if [[ -n "${!var_name:-}" ]]; then
    echo "set (redacted)"
  else
    echo "missing"
  fi
}

check_required() {
  local missing=0
  local v
  for v in "$@"; do
    if [[ -z "${!v:-}" ]]; then
      echo "Missing required env var: $v" >&2
      missing=1
    fi
  done
  return "$missing"
}

check_either_or() {
  local left="$1"
  local right="$2"
  if [[ -n "${!left:-}" || -n "${!right:-}" ]]; then
    return 0
  fi
  echo "Missing required env vars: at least one of $left or $right must be set" >&2
  return 1
}

check_pair_or() {
  local single="$1"
  local pair_a="$2"
  local pair_b="$3"
  if [[ -n "${!single:-}" ]]; then
    return 0
  fi
  if [[ -n "${!pair_a:-}" && -n "${!pair_b:-}" ]]; then
    return 0
  fi
  echo "Missing required env vars: set $single or set both $pair_a and $pair_b" >&2
  return 1
}

run_or_print() {
  local cmd="$1"
  if [[ "$dry_run" == "1" ]]; then
    echo "[DRY-RUN] $cmd"
  else
    echo "[RUN] $cmd"
    eval "$cmd"
  fi
}

android_cmds=(
  "pytest tests/real_env/android/test_android_webview_switch_smoke.py::test_android_webview_switch_smoke_validate_extract_real_env -q"
  "pytest tests/real_env/android/test_android_webview_switch_smoke.py::test_android_webview_switch_reporting_artifacts_are_safe -q"
)

ios_cmds=(
  "pytest tests/real_env/ios/test_ios_webview_switch_smoke.py::test_ios_webview_switch_smoke_validate_extract_real_env -q"
  "pytest tests/real_env/ios/test_ios_webview_switch_smoke.py::test_ios_webview_switch_reporting_artifacts_are_safe -q"
)

cloud_cmds=(
  "pytest tests/real_env/cloud/test_cloud_webview_switch_smoke.py::test_cloud_webview_switch_smoke_validate_extract_real_env -q"
  "pytest tests/real_env/cloud/test_cloud_webview_switch_smoke.py::test_cloud_webview_switch_reporting_artifacts_are_safe -q"
)

validate_android() {
  local ok=0
  check_required \
    BUBBLEGUM_REAL_ENV \
    BUBBLEGUM_APPIUM_SERVER_URL \
    BUBBLEGUM_ANDROID_DEVICE_NAME \
    BUBBLEGUM_ANDROID_WEBVIEW_SWITCH_SMOKE \
    BUBBLEGUM_ANDROID_WEBVIEW_VALIDATE_TEXT \
    BUBBLEGUM_ANDROID_WEBVIEW_EXTRACT_REF \
    BUBBLEGUM_ANDROID_WEBVIEW_REQUIRE_SWITCH || ok=1
  check_pair_or BUBBLEGUM_ANDROID_APP BUBBLEGUM_ANDROID_PACKAGE BUBBLEGUM_ANDROID_ACTIVITY || ok=1
  return "$ok"
}

validate_ios() {
  local ok=0
  check_required \
    BUBBLEGUM_REAL_ENV \
    BUBBLEGUM_APPIUM_SERVER_URL \
    BUBBLEGUM_IOS_DEVICE_NAME \
    BUBBLEGUM_IOS_WEBVIEW_SWITCH_SMOKE \
    BUBBLEGUM_IOS_WEBVIEW_VALIDATE_TEXT \
    BUBBLEGUM_IOS_WEBVIEW_EXTRACT_REF \
    BUBBLEGUM_IOS_WEBVIEW_REQUIRE_SWITCH || ok=1
  check_either_or BUBBLEGUM_IOS_APP BUBBLEGUM_IOS_BUNDLE_ID || ok=1
  return "$ok"
}

validate_cloud() {
  local ok=0
  check_required \
    BUBBLEGUM_REAL_ENV \
    BUBBLEGUM_CLOUD_DEVICE \
    BUBBLEGUM_CLOUD_PROVIDER \
    BUBBLEGUM_CLOUD_USERNAME \
    BUBBLEGUM_CLOUD_ACCESS_KEY \
    BUBBLEGUM_CLOUD_PLATFORM \
    BUBBLEGUM_CLOUD_DEVICE_NAME \
    BUBBLEGUM_CLOUD_WEBVIEW_SWITCH_SMOKE \
    BUBBLEGUM_CLOUD_WEBVIEW_VALIDATE_TEXT \
    BUBBLEGUM_CLOUD_WEBVIEW_EXTRACT_REF \
    BUBBLEGUM_CLOUD_WEBVIEW_REQUIRE_SWITCH || ok=1
  check_either_or BUBBLEGUM_CLOUD_APP BUBBLEGUM_CLOUD_APP_ID || ok=1
  return "$ok"
}

print_checks_for() {
  local target="$1"
  echo "Environment check for $target:"
  case "$target" in
    android)
      for var in \
        BUBBLEGUM_REAL_ENV BUBBLEGUM_APPIUM_SERVER_URL BUBBLEGUM_ANDROID_DEVICE_NAME \
        BUBBLEGUM_ANDROID_APP BUBBLEGUM_ANDROID_PACKAGE BUBBLEGUM_ANDROID_ACTIVITY \
        BUBBLEGUM_ANDROID_WEBVIEW_SWITCH_SMOKE BUBBLEGUM_ANDROID_WEBVIEW_VALIDATE_TEXT \
        BUBBLEGUM_ANDROID_WEBVIEW_EXTRACT_REF BUBBLEGUM_ANDROID_WEBVIEW_REQUIRE_SWITCH; do
        echo "  - $var: $(redacted_status "$var")"
      done
      ;;
    ios)
      for var in \
        BUBBLEGUM_REAL_ENV BUBBLEGUM_APPIUM_SERVER_URL BUBBLEGUM_IOS_DEVICE_NAME \
        BUBBLEGUM_IOS_APP BUBBLEGUM_IOS_BUNDLE_ID BUBBLEGUM_IOS_WEBVIEW_SWITCH_SMOKE \
        BUBBLEGUM_IOS_WEBVIEW_VALIDATE_TEXT BUBBLEGUM_IOS_WEBVIEW_EXTRACT_REF \
        BUBBLEGUM_IOS_WEBVIEW_REQUIRE_SWITCH BUBBLEGUM_IOS_PLATFORM_VERSION \
        BUBBLEGUM_IOS_AUTOMATION_NAME; do
        echo "  - $var: $(redacted_status "$var")"
      done
      ;;
    cloud)
      for var in \
        BUBBLEGUM_REAL_ENV BUBBLEGUM_CLOUD_DEVICE BUBBLEGUM_CLOUD_PROVIDER \
        BUBBLEGUM_CLOUD_USERNAME BUBBLEGUM_CLOUD_ACCESS_KEY BUBBLEGUM_CLOUD_PLATFORM \
        BUBBLEGUM_CLOUD_DEVICE_NAME BUBBLEGUM_CLOUD_APP BUBBLEGUM_CLOUD_APP_ID \
        BUBBLEGUM_CLOUD_WEBVIEW_SWITCH_SMOKE BUBBLEGUM_CLOUD_WEBVIEW_VALIDATE_TEXT \
        BUBBLEGUM_CLOUD_WEBVIEW_EXTRACT_REF BUBBLEGUM_CLOUD_WEBVIEW_REQUIRE_SWITCH; do
        echo "  - $var: $(redacted_status "$var")"
      done
      ;;
  esac
}

run_platform() {
  local target="$1"
  local valid=0

  print_checks_for "$target"

  if [[ "$dry_run" != "1" ]]; then
    case "$target" in
      android) validate_android || valid=1 ;;
      ios) validate_ios || valid=1 ;;
      cloud) validate_cloud || valid=1 ;;
    esac
    if [[ "$valid" -ne 0 ]]; then
      echo "Aborting due to missing required environment for $target." >&2
      exit 1
    fi
  fi

  case "$target" in
    android)
      for cmd in "${android_cmds[@]}"; do run_or_print "$cmd"; done
      ;;
    ios)
      for cmd in "${ios_cmds[@]}"; do run_or_print "$cmd"; done
      ;;
    cloud)
      for cmd in "${cloud_cmds[@]}"; do run_or_print "$cmd"; done
      ;;
  esac
}

if [[ "$platform" == "all" ]]; then
  run_platform android
  run_platform ios
  run_platform cloud
else
  run_platform "$platform"
fi
