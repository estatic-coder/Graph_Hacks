from fastapi import FastAPI
from db import get_user
from utils import format_user_data

app = FastAPI()

@app.get("/users/{user_id}")
def read_user(user_id: int):
    user_row = get_user(user_id)
    return format_user_data(user_row)
