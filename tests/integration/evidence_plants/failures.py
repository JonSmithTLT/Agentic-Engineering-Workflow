"""Deliberate assertion failures selected only by the evidence workflow."""

import os
import random
import string
import threading


def scanner_fixtures():
    # gitleaks v8.28.0 cmd/generate/config/rules/{github,privatekey}.go. The PAT rule generates
    # a 36-character alphanumeric suffix. The deliberately incomplete PEM is the upstream positive test.
    token = "ghp_" + "".join(random.Random(841).choices(string.ascii_letters + string.digits, k=36))
    pem = "\n".join(("-----BEGIN " + "PRIVATE KEY-----",
                     "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDAC4AWkdwKYSd8",
                     "Ks14IReLcYgADhoXk56ZzXI=", "-----END " + "PRIVATE KEY-----"))
    return token, pem


def test_list_difference():
    left = ["shared entry"] * 60
    right = left.copy()
    left[30], right[30] = "actual middle entry", "expected middle entry"
    assert left == right


def test_string_difference():
    prefix = "common prefix " * 80
    assert prefix + "actual string suffix" == prefix + "expected string suffix"


def test_full_masked_failure():
    token, pem = scanner_fixtures()
    explanation = "ordinary comparison context\n" * 3500
    raise AssertionError(f"overflow begins\n{token}\n{pem}\n{explanation}overflow ends")


def test_session_after_failure():
    if os.environ["AEW_EVIDENCE_PLANT"] == "failure-in-death":
        threading.Event().wait(600)
