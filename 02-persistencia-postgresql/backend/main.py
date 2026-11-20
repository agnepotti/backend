import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)

class Task(BaseModel):
    id: int
    title: str
    completed: bool
    created_at: str

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
pool = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=10, open=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    yield
    pool.close()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def serialize_task(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "completed": row["completed"],
        "created_at": row["created_at"].isoformat(),
    }

@app.get("/api/tasks", response_model=list[Task])
def list_tasks():
    with pool.connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, completed, created_at FROM tasks ORDER BY id")
            rows = cur.fetchall()
    return [serialize_task(row) for row in rows]

@app.post("/api/tasks", response_model=Task, status_code=201)
def create_task(body: TaskCreate):
    with pool.connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tasks (title) VALUES (%s) RETURNING id, title, completed, created_at",
                (body.title.strip(),),
            )
            row = cur.fetchone()
    return serialize_task(row)

@app.patch("/api/tasks/{task_id}", response_model=Task)
def toggle_task(task_id: int):
    with pool.connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tasks SET completed = NOT completed WHERE id = %s RETURNING id, title, completed, created_at",
                (task_id,),
            )
            row = cur.fetchone()
    if not row: raise HTTPException(status_code=404, detail="No encontrada")
    return serialize_task(row)

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tasks WHERE id = %s RETURNING id", (task_id,))
            row = cur.fetchone()
    if not row: raise HTTPException(status_code=404, detail="No encontrada")
    return {"ok": True}

@app.get("/api/health")
def health_check():
    with pool.connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM tasks")
            count = cur.fetchone()["total"]
    return {"status": "Funciona", "db": "conectada", "tasks_count": count}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)