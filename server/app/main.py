from fastapi import FastAPI

# FastAPI 앱 생성
app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "AI 서버가 성공적으로 실행되었습니다."}

@app.get("/api/v1/hello")
def get_hello():
    return {"service": "main-project-ai", "status": "ok"}