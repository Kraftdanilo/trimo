"""Point d'entrée HyperFrames : python run.py → http://localhost:8080."""
import uvicorn

if __name__ == "__main__":
    print("HyperFrames — studio disponible sur http://localhost:8080")
    uvicorn.run("server:app", host="127.0.0.1", port=8080, reload=True)
