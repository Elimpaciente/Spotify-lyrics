from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import hashlib
import hmac
import math
import re
from urllib.parse import urlparse
from typing import Optional
import requests # Añadido para el get_secret_version original
import spotipy # Añadido para la integración con spotipy

app = FastAPI(title="Spotify Lyrics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
TOKEN_URL = 'https://open.spotify.com/api/token'
SERVER_TIME_URL = 'https://open.spotify.com/api/server-time'
SPOTIFY_HOME_PAGE_URL = "https://open.spotify.com/"
CLIENT_VERSION = "1.2.46.25.g7f189073"

HEADERS = {
    "accept": "application/json",
    "accept-language": "en-US",
    "content-type": "application/json",
    "origin": SPOTIFY_HOME_PAGE_URL,
    "priority": "u=1, i",
    "referer": SPOTIFY_HOME_PAGE_URL,
    "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "spotify-app-version": CLIENT_VERSION,
    "app-platform": "WebPlayer",
}

# Spotify sp_dc cookie - DEBES REEMPLAZAR ESTO CON TU PROPIA COOKIE sp_dc
# Puedes obtenerla iniciando sesión en open.spotify.com en tu navegador, abriendo las herramientas de desarrollador,
# y buscando la cookie 'sp_dc' en la sección de 'Application' -> 'Cookies'.
DEFAULT_SP_DC = "AQAO1j7bPbFcbVh5TbQmwmTd_XFckJhbOipaA0t2BZpViASzI6Qrk1Ty0WviN1K1mmJv_hV7xGVbMPHm4-HAZbs3OXOHSu38Xq7hZ9wqWwvdZwjiWTQmKWLoKxJP1j3kI7-8eWgVZ8TcPxRnXrjP3uDJ9SnzOla_EpxePC74dHa5D4nBWWfFLdiV9bMQuzUex6izb12gCh0tvTt3Xlg"

class TOTP:
    def __init__(self) -> None:
        self.secret, self.version = None, None
        
    async def initialize(self):
        self.secret, self.version = await self.get_secret_version()
        self.period = 30
        self.digits = 6
        return self

    def generate(self, timestamp: int) -> str:
        counter = math.floor(timestamp / 1000 / self.period)
        counter_bytes = counter.to_bytes(8, byteorder="big")

        h = hmac.new(self.secret, counter_bytes, hashlib.sha1)
        hmac_result = h.digest()

        offset = hmac_result[-1] & 0x0F
        binary = (
            (hmac_result[offset] & 0x7F) << 24
            | (hmac_result[offset + 1] & 0xFF) << 16
            | (hmac_result[offset + 2] & 0xFF) << 8
            | (hmac_result[offset + 3] & 0xFF)
        )

        return str(binary % (10**self.digits)).zfill(self.digits)
    
    async def get_secret_version(self) -> tuple:
        # Cambiado a httpx.AsyncClient para consistencia
        async with httpx.AsyncClient(timeout=15.0) as client:
            req = await client.get("https://raw.githubusercontent.com/Thereallo1026/spotify-secrets/refs/heads/main/secrets/secrets.json")
            if req.status_code != 200:
                raise ValueError("Failed to fetch TOTP secret and version.")
            data = req.json()[-1]
            ascii_codes = [ord(c) for c in data['secret']]
            transformed = [val ^ ((i % 33) + 9) for i, val in enumerate(ascii_codes)]
            secret_key = "".join(str(num) for num in transformed)
            return bytes(secret_key, 'utf-8'), data['version']

class SpotifyLyricsAPI:
    def __init__(self, sp_dc: str = DEFAULT_SP_DC) -> None:
        self.sp_dc = sp_dc
        self.token = None
        self.totp = None
        self.sp = None # Inicializar spotipy aquí

    async def initialize(self):
        self.totp = await TOTP().initialize()
        await self._login()
        # Inicializar spotipy después de obtener el token
        self.sp = spotipy.Spotify(auth=self.token)
        return self

    async def _login(self):
        async with httpx.AsyncClient(timeout=15.0) as client:
            client.cookies.set('sp_dc', self.sp_dc)
            client.headers.update(HEADERS)
            
            server_time_response = await client.get(SERVER_TIME_URL)
            server_time = 1e3 * server_time_response.json()["serverTime"]
            totp = self.totp.generate(timestamp=server_time)
            
            params = {
                "reason": "init",
                "productType": "web-player",
                "totp": totp,
                "totpVer": str(self.totp.version),
                "ts": str(server_time),
            }
            
            req = await client.get(TOKEN_URL, params=params)
            token = req.json()
            self.token = token['accessToken']

    def extract_track_id(self, url: str) -> str:
        if not url:
            raise ValueError("No track URL provided")
        
        if re.match(r'^[a-zA-Z0-9]{22}$', url):
            return url
            
        parsed = urlparse(url)
        if parsed.netloc.endswith('spotify.com'):
            path_parts = parsed.path.split('/')
            if len(path_parts) >= 3 and path_parts[1] == 'track':
                return path_parts[2]
        
        raise ValueError("Invalid Spotify track URL")

    async def get_track_details(self, track_id: str) -> dict:
        # Usar self.sp para obtener detalles de la pista
        try:
            track = self.sp.track(track_id)
            return track
        except Exception as e:
            raise ValueError(f"Track not found: {str(e)}")

    async def get_lyrics(self, track_id: str) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            client.cookies.set('sp_dc', self.sp_dc)
            client.headers.update(HEADERS)
            client.headers.update({'authorization': f'Bearer {self.token}'})
            
            params = 'format=json&market=from_token'
            req = await client.get(
                f'https://spclient.wg.spotify.com/color-lyrics/v2/track/{track_id}',
                params=params
            )
            if req.status_code != 200:
                return None
            return req.json()

    def get_combined_lyrics(self, lines: list) -> str:
        if not lines:
            return "No lyrics available"
        return '\n'.join([line['words'] for line in lines])

@app.get("/")
async def root():
    return JSONResponse(
        content={
            "status_code": 400,
            "message": "The url parameter is required to get the lyrics",
            "developer": "El Impaciente",
            "telegram_channel": "https://t.me/Apisimpacientes",
            "usage": "Use /lyrics?url=https://open.spotify.com/track/TRACK_ID"
        },
        status_code=400
    )

@app.get("/lyrics")
async def get_lyrics_endpoint(url: str = Query(..., description="Spotify track URL")):
    if not url or url.strip() == "":
        return JSONResponse(
            content={
                "status_code": 400,
                "message": "The url parameter is required to get the lyrics",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes",
                "example": "/lyrics?url=https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp"
            },
            status_code=400
        )
    
    try:
        spotify = await SpotifyLyricsAPI().initialize()
        track_id = spotify.extract_track_id(url)
        
        track_details = await spotify.get_track_details(track_id)
        lyrics_data = await spotify.get_lyrics(track_id)
        
        song_title = track_details['name']
        artist_name = track_details['artists'][0]['name']
        
        lyrics_text = spotify.get_combined_lyrics(
            lyrics_data['lyrics']['lines'] if lyrics_data and 'lyrics' in lyrics_data else []
        )
        
        response_content = {
            "status_code": 200,
            "message": "Lyrics retrieved successfully",
            "title": song_title,
            "artist": artist_name,
            "lyrics": lyrics_text,
            "developer": "El Impaciente",
            "telegram_channel": "https://t.me/Apisimpacientes"
        }
        
        return JSONResponse(
            content=response_content,
            status_code=200
        )
        
    except ValueError as e:
        return JSONResponse(
            content={
                "status_code": 400,
                "message": f"Error: {str(e)}",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=400
        )
    except Exception as e:
        return JSONResponse(
            content={
                "status_code": 400,
                "message": "Error getting lyrics. Please try again.",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=400
        )
