"""Fixed load scenario contract for Locust or equivalent runner."""

SCENARIO = {
    "warmup": {"events_per_second": 100, "duration_seconds": 900},
    "burst": {"events_per_second": 300, "duration_seconds": 60},
    "duplicates": True,
    "signed_events": True,
    "external_services": "fake",
    "count_unit": "individual_events",
}


if __name__ == "__main__":
    import json
    print(json.dumps(SCENARIO, indent=2))
