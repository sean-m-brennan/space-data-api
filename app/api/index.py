#  Copyright 2024 Sean M. Brennan and contributors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import json
import logging
import os
import ssl
import traceback
from typing import Annotated
import secrets
from datetime import datetime, timedelta, UTC
from http.client import HTTPException
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from starlette.responses import HTMLResponse
from passlib.context import CryptContext
import pyseto
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import utc

from .spice_converter import SpiceQuery


this_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(this_dir)

def get_key():
    key_num_bytes = 32
    return pyseto.Key.new(version=4, purpose="local", key=secrets.token_bytes(key_num_bytes))

secret_key = get_key()
logger = logging.getLogger('uvicorn.error')
spice = SpiceQuery(jit=True)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
crypto_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
scheduler = AsyncIOScheduler(timezone=utc)

origins = ["*"]  # TODO use specific requester IPs here (anti-DDOS), preferably from config file

with open(os.path.join(this_dir, 'users.json')) as f:
    users_db = json.load(f)


def new_token(info: dict, expire_seconds: Optional[int] = 60 * 60 * 24) -> bytes:
    data = info.copy()
    dt = datetime.now(UTC) + timedelta(seconds=expire_seconds)
    data.update({'expires_at': dt.timestamp()})
    return pyseto.encode(secret_key, payload=data, serializer=json)


def authenticate(payload: bytes = Depends(oauth2_scheme)):
    token = json.loads(payload)['access_token']
    decoded = pyseto.decode(secret_key, token=token, deserializer=json).payload
    if not decoded.get('expires_at', 0) > datetime.now(UTC).timestamp():
        raise HTTPException(status_code=403, detail='Invalid credentials')


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,  # noqa
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(os.path.join(app_dir, 'cert.pem'), keyfile=os.path.join(app_dir, 'key.pem'))


@app.get('/login')
async def login():  # OAuth2 password flow
    html = '''
        <form method="POST" action="/token">
            <label for="username">Username/Email:</label>
            <input id="username" type="text" name="username"/><br/>
            <label for="password">Password:</label>
            <input id="password" type="password" name="password"/><br/>
            <input type="submit" value="Submit"/>
        </form>
    '''
    return HTMLResponse(html)


@app.post("/token")
async def auth(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    pwd_hash = users_db.get(form_data.username)
    if not pwd_hash:
        raise HTTPException(status_code=403, detail='Invalid credentials')
    if not crypto_context.verify(form_data.password, pwd_hash):
        raise HTTPException(status_code=403, detail='Invalid credentials')
    token = new_token({'user': form_data.username})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/check")
async def check_connection():
    return {}


@app.get("/convert/", dependencies=[Depends(authenticate)])
async def convert_coords(ident: str, coords: str, original: str, new: str, dt_str: str):
    authenticate()
    try:
        if original.upper() not in ['ITRF93', 'J2000'] or new.upper() not in ['ITRF93', 'J2000']:
            return {'ident': ident, 'error': 'Unsupported conversion %s => %s' % (original, new)}
        position = json.loads(coords)
        dt = datetime.fromisoformat(dt_str)
        coords = spice.transform_coordinates(position, original.upper(), new.upper(), dt)
        return {'ident': ident, 'coordinates': coords}
    except Exception as e:
        logger.error(traceback.format_exc())
        return {'ident': ident, 'error': str(e)}


@app.get("/fixed2j2k/", dependencies=[Depends(authenticate)])
async def fixed_to_j2k(ident: str, lat: float, lon: float, alt: float, dt_str: str):
    try:
        dt = datetime.fromisoformat(dt_str)
        coords = spice.fixed_to_j2000(lat, lon, alt, dt)
        return {'ident': ident, 'coordinates': coords}
    except Exception as e:
        logger.error(traceback.format_exc())
        return {'ident': ident, 'error': str(e)}


@app.get("/position/", dependencies=[Depends(authenticate)])
async def body_position(ident: str, body: str, dt_str: str):
    try:
        dt = datetime.fromisoformat(dt_str)
        #if body.lower() == 'sun':
        #    coords = sun_position(dt)
        #else:
        coords = spice.celestial_position(body, dt)
        return {'ident': ident, 'position': coords}
    except Exception as e:
        logger.error(traceback.format_exc())
        return {'ident': ident, 'error': str(e)}


@scheduler.scheduled_job('cron', hour=0, minute=30)
async def rotate_secret_key():
    global secret_key
    secret_key = get_key()
    logger.warning("Key changed")
