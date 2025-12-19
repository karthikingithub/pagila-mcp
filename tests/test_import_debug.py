def test_import_paths_and_module():
    import sys

    print("PYTEST CWD:", __import__("os").getcwd())
    print("sys.path[0]:", sys.path[0])
    print("sys.path sample:", sys.path[:5])
    try:
        import mcp_pagila_server as _mcp

        print("imported mcp_pagila_server OK")
        assert _mcp is not None
    except Exception as e:
        print("import error:", type(e).__name__, e)
        raise
