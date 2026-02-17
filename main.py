from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Person Counter API Running"}
