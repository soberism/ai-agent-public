"""安排儿后端。"""


def main() -> None:
    import uvicorn

    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, proxy_headers=False)
