from fastapi import FastAPI

from studyflow.routers.auth import router as auth_router
from studyflow.routers.calendar import router as calendar_router
from studyflow.routers.series import router as series_router
from studyflow.routers.subjects import router as subjects_router
from studyflow.routers.tasks import router as tasks_router
from studyflow.routers.time_blocks import router as time_blocks_router

app = FastAPI()
app.include_router(auth_router, prefix="/api/v1")
app.include_router(subjects_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(series_router, prefix="/api/v1")
app.include_router(time_blocks_router, prefix="/api/v1")
app.include_router(calendar_router, prefix="/api/v1")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
