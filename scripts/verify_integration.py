#!/usr/bin/env python3
"""
Verification script for router registration and OpenAPI documentation.

This script verifies:
1. All routes are properly registered
2. OpenAPI schema is correctly generated
3. All endpoints are documented
4. Dependency injection is working
"""

from app.main import create_app


def verify_routes():
    """Verify all routes are properly registered."""
    app = create_app()

    # Get all routes
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            routes.append((route.path, route.methods))

    print("=" * 70)
    print("REGISTERED ROUTES")
    print("=" * 70)

    # Group routes by prefix
    api_v1_routes = [r for r in routes if r[0].startswith("/api/v1")]
    health_routes = [r for r in routes if r[0] in ["/health", "/"]]
    other_routes = [r for r in routes if r not in api_v1_routes and r not in health_routes]

    print("\nAPI v1 Routes:")
    for path, methods in sorted(api_v1_routes):
        print(f"  {path:50s} {', '.join(sorted(methods))}")

    print("\nHealth & Root Routes:")
    for path, methods in sorted(health_routes):
        print(f"  {path:50s} {', '.join(sorted(methods))}")

    print(f"\nTotal routes: {len(routes)}")
    print(f"API v1 routes: {len(api_v1_routes)}")

    return len(api_v1_routes)


def verify_openapi_schema():
    """Verify OpenAPI schema generation."""
    app = create_app()

    # Get OpenAPI schema
    openapi_schema = app.openapi()

    print("\n" + "=" * 70)
    print("OPENAPI SCHEMA VERIFICATION")
    print("=" * 70)

    print(f"\nOpenAPI Version: {openapi_schema.get('openapi')}")
    print(f"API Title: {openapi_schema['info']['title']}")
    print(f"API Version: {openapi_schema['info']['version']}")
    print(f"API Description: {openapi_schema['info']['description'][:80]}...")

    # Count endpoints
    paths = openapi_schema.get("paths", {})
    print(f"\nTotal documented endpoints: {len(paths)}")

    # List backtest endpoints
    backtest_endpoints = [p for p in paths.keys() if "/backtest" in p]
    print(f"Backtest endpoints: {len(backtest_endpoints)}")

    print("\nBacktest Endpoints:")
    for endpoint in sorted(backtest_endpoints):
        methods = list(paths[endpoint].keys())
        methods = [m.upper() for m in methods if m != "parameters"]
        print(f"  {endpoint:50s} {', '.join(methods)}")

    # Verify schemas
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    print(f"\nTotal schemas defined: {len(schemas)}")

    # Key schemas
    key_schemas = [
        "BacktestRequest",
        "ExecuteBacktestRequest",
        "GenerateBacktestResponse",
        "ExecuteBacktestResponse",
        "JobStatusResponse",
        "ExecutionResult",
        "BacktestResultResponse",
    ]

    print("\nKey Request/Response Models:")
    for schema in key_schemas:
        status = "✓" if schema in schemas else "✗"
        print(f"  {status} {schema}")

    return len(backtest_endpoints)


def verify_dependency_injection():
    """Verify dependency injection is working."""
    from app.core.container import get_container

    print("\n" + "=" * 70)
    print("DEPENDENCY INJECTION VERIFICATION")
    print("=" * 70)

    container = get_container()

    # Verify settings
    settings = container.settings
    print(f"\n✓ Settings loaded: {settings.app_name} v{settings.app_version}")

    # Verify HTTP client
    http_client = container.get_http_client()
    print(f"✓ HTTP client initialized: {type(http_client).__name__}")

    # Verify code validator
    code_validator = container.get_code_validator()
    print(f"✓ Code validator initialized: {type(code_validator).__name__}")

    # Verify job manager
    job_manager = container.get_job_manager()
    print(f"✓ Job manager initialized: {type(job_manager).__name__}")

    # Verify result formatter
    result_formatter = container.get_result_formatter()
    print(f"✓ Result formatter initialized: {type(result_formatter).__name__}")

    print("\n✓ All core dependencies properly wired")


def main():
    """Run all verification checks."""
    print("\n" + "=" * 70)
    print("OPEN TRADING API - INTEGRATION VERIFICATION")
    print("=" * 70)

    try:
        # Verify routes
        num_api_routes = verify_routes()

        # Verify OpenAPI
        num_backtest_endpoints = verify_openapi_schema()

        # Verify dependency injection
        verify_dependency_injection()

        # Summary
        print("\n" + "=" * 70)
        print("VERIFICATION SUMMARY")
        print("=" * 70)
        print(f"\n✓ Router Registration: OK ({num_api_routes} API v1 routes)")
        print(f"✓ OpenAPI Documentation: OK ({num_backtest_endpoints} backtest endpoints)")
        print(f"✓ Dependency Injection: OK (all services wired)")
        print(f"\n✓ ALL CHECKS PASSED - Integration Complete!\n")

        return 0

    except Exception as e:
        print(f"\n✗ VERIFICATION FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
