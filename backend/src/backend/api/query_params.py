from starlette.requests import Request


def allowed_queries(request: Request) -> bool:
    path = request.url.path
    keys = set(request.query_params)
    if request.method == "GET":
        if path in (
            "/api/todos",
            "/api/calendar/events",
            "/api/planning/review",
            "/api/contacts",
            "/api/documents/review-items",
            "/api/documents/search",
            "/api/hub/search",
        ):
            return True
        if path == "/api/sharing/states":
            return keys <= {"resources"}
    return (
        path == "/api/life/shopping-lists"
        or path.startswith("/api/life/shopping-lists/")
    ) and keys <= {"meal_id"}
