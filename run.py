"""Start the Debug Dojo API."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("dojo.api:app", host="0.0.0.0", port=8000)
