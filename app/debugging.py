# This file is specifically for debugging from the IDE
import uvicorn

if __name__ == "__main__":
    uvicorn.run('main:app', host='0.0.0.0', port=8000)
