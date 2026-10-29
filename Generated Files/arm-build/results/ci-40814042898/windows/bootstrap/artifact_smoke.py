import fastapi
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pathlib import Path
assert not Path(fastapi.__file__).is_relative_to(Path('C:\\a\\fastapi\\fastapi\\fastapi'))
app = FastAPI()
@app.get('/items/{item_id}')
def read(item_id: int):
    return {'item_id': item_id}
with TestClient(app) as client:
    assert client.get('/items/7').json() == {'item_id': 7}
    assert client.get('/items/invalid').status_code == 422
    assert client.get('/openapi.json').status_code == 200
print(fastapi.__file__)
